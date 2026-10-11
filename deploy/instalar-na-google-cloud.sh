#!/usr/bin/env bash
# Instala (ou atualiza) o onlinebusinesses na Google Cloud. Quem corre isto é o Claude, na sessão cloud, sem
# interação e sem SSH (a sessão só tem saída HTTPS): bash deploy/instalar-na-google-cloud.sh
#
# Entradas (variáveis de ambiente da sessão; nada é pedido nem escrito no ecrã):
#   GCP_SA_KEY                chave JSON de uma conta de serviço com papel Owner no projeto (obrigatória)
#   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY (obrigatórias); LLM_MODEL (recomendada)
#   BRAVE_API_KEY, INSTAGRAM_USER_ID, INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID_ES, INSTAGRAM_ACCESS_TOKEN_ES,
#   TIKTOK_ACCESS_TOKEN, TIKTOK_ACCESS_TOKEN_ES (opcionais)
#   GOOGLE_CLOUD_PROJECT (opcional: por omissão o project_id da chave), VERTEX_LOCATION, IMAGEN_MODEL,
#   TTS_VOICE_PT, TTS_VOICE_ES, PUBLISH_LANGUAGES (valores por omissão abaixo)
#
# O que faz: empacota o código (git archive HEAD: só o que está commitado) para um bucket PRIVADO de deploy; guarda os
# segredos num só segredo do Secret Manager (`onlinebusinesses-env`, versão nova a cada execução); cria o bucket público
# dos vídeos, a conta de serviço da app (papéis mínimos) e uma VM e2-micro do nível gratuito cujo `startup-script`, a
# cada arranque, instala o necessário, descarrega o código e o segredo e instala o cron. Repetir o script atualiza tudo
# sem duplicar recursos e reinicia a VM (`instances reset`) para aplicar a nova versão.
# Nível gratuito e regiões consultados a 2026-10-10 (docs/compliance.md).
set -euo pipefail

REGION="${REGION:-us-central1}"              # nível gratuito da Compute Engine: us-west1, us-central1 ou us-east1
ZONE="${ZONE:-${REGION}-a}"
VM="${VM_NAME:-onlinebusinesses}"
SA_NAME="onlinebusinesses"
SECRET="onlinebusinesses-env"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }

missing=""
for name in GCP_SA_KEY TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID ANTHROPIC_API_KEY; do
  if [ -z "${!name:-}" ]; then missing="$missing $name"; fi
done
[ -z "$missing" ] || die "faltam variáveis de ambiente obrigatórias:$missing (ver docs/setup-ricardo.md)"
command -v gcloud >/dev/null || die "gcloud não encontrado."
command -v git >/dev/null || die "git não encontrado."

WORK="$(mktemp -d)"
KEY_FILE="$WORK/sa-key.json"
cleanup() {
  gcloud auth revoke --all >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT
umask 077
printf '%s' "$GCP_SA_KEY" >"$KEY_FILE"

say "A autenticar com a conta de serviço"
gcloud auth activate-service-account --key-file="$KEY_FILE" >/dev/null 2>&1 || die "a chave GCP_SA_KEY não é válida."
GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["project_id"])' "$KEY_FILE")}"
gcloud config set project "$GOOGLE_CLOUD_PROJECT" >/dev/null

# Valores por omissão do código (podem ser sobrepostos pelo ambiente).
VERTEX_LOCATION="${VERTEX_LOCATION:-us-central1}"
IMAGEN_MODEL="${IMAGEN_MODEL:-imagen-4.0-generate-001}"
TTS_VOICE_PT="${TTS_VOICE_PT:-pt-PT-Wavenet-F}"
TTS_VOICE_ES="${TTS_VOICE_ES:-es-ES-Neural2-F}"
PUBLISH_LANGUAGES="${PUBLISH_LANGUAGES:-pt-PT,es}"
GCS_BUCKET="${GCS_BUCKET:-${GOOGLE_CLOUD_PROJECT}-onlinebusinesses-videos}"
DEPLOY_BUCKET="${GOOGLE_CLOUD_PROJECT}-onlinebusinesses-deploy"
DB_PATH="/var/lib/onlinebusinesses/onlinebusinesses.sqlite"
OUT_DIR="/var/lib/onlinebusinesses/out"
SA_EMAIL="${SA_NAME}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"

say "A ativar as APIs (Compute Engine, Text-to-Speech, Vertex AI, Cloud Storage, Secret Manager)"
gcloud services enable compute.googleapis.com texttospeech.googleapis.com aiplatform.googleapis.com \
  storage.googleapis.com iam.googleapis.com secretmanager.googleapis.com

say "Bucket público dos vídeos: gs://$GCS_BUCKET"
if ! gcloud storage buckets describe "gs://$GCS_BUCKET" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$GCS_BUCKET" --location="$REGION" --uniform-bucket-level-access
fi
# Leitura pública dos objetos (allUsers:objectViewer); se uma política da organização o bloquear, o Instagram não os lê.
gcloud storage buckets add-iam-policy-binding "gs://$GCS_BUCKET" --member=allUsers \
  --role=roles/storage.objectViewer >/dev/null || die "não foi possível tornar o bucket público (política da organização?)."

say "Bucket PRIVADO do código: gs://$DEPLOY_BUCKET"
if ! gcloud storage buckets describe "gs://$DEPLOY_BUCKET" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$DEPLOY_BUCKET" --location="$REGION" --uniform-bucket-level-access \
    --public-access-prevention
fi

say "Conta de serviço da app com os papéis mínimos: $SA_EMAIL"
if ! gcloud iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SA_NAME" --display-name="onlinebusinesses"
fi
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" --member="serviceAccount:$SA_EMAIL" \
  --role=roles/aiplatform.user --condition=None >/dev/null
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" --member="serviceAccount:$SA_EMAIL" \
  --role=roles/serviceusage.serviceUsageConsumer --condition=None >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$GCS_BUCKET" --member="serviceAccount:$SA_EMAIL" \
  --role=roles/storage.objectAdmin >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$DEPLOY_BUCKET" --member="serviceAccount:$SA_EMAIL" \
  --role=roles/storage.objectViewer >/dev/null

say "A empacotar o código (git archive HEAD) e a enviar para o bucket privado"
git -C "$REPO_DIR" archive --format=tar.gz HEAD -o "$WORK/app.tar.gz"
gcloud storage cp "$WORK/app.tar.gz" "gs://$DEPLOY_BUCKET/app.tar.gz" >/dev/null

say "Segredos: nova versão de $SECRET no Secret Manager"
ENV_FILE="$WORK/onlinebusinesses.env"
: >"$ENV_FILE"
{
  printf 'GOOGLE_CLOUD_PROJECT=%s\nGCS_BUCKET=%s\nVERTEX_LOCATION=%s\nIMAGEN_MODEL=%s\n' \
    "$GOOGLE_CLOUD_PROJECT" "$GCS_BUCKET" "$VERTEX_LOCATION" "$IMAGEN_MODEL"
  printf 'TTS_VOICE_PT=%s\nTTS_VOICE_ES=%s\nPUBLISH_LANGUAGES=%s\nDB_PATH=%s\nOUT_DIR=%s\n' \
    "$TTS_VOICE_PT" "$TTS_VOICE_ES" "$PUBLISH_LANGUAGES" "$DB_PATH" "$OUT_DIR"
} >>"$ENV_FILE"
for name in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID ANTHROPIC_API_KEY LLM_MODEL BRAVE_API_KEY INSTAGRAM_USER_ID \
  INSTAGRAM_ACCESS_TOKEN INSTAGRAM_USER_ID_ES INSTAGRAM_ACCESS_TOKEN_ES TIKTOK_ACCESS_TOKEN TIKTOK_ACCESS_TOKEN_ES; do
  if [ -n "${!name:-}" ]; then printf '%s=%s\n' "$name" "${!name}" >>"$ENV_FILE"; fi
done
if ! gcloud secrets describe "$SECRET" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET" --replication-policy=automatic >/dev/null
fi
gcloud secrets add-iam-policy-binding "$SECRET" --member="serviceAccount:$SA_EMAIL" \
  --role=roles/secretmanager.secretAccessor >/dev/null
gcloud secrets versions add "$SECRET" --data-file="$ENV_FILE" >/dev/null

# Script de arranque da VM: corre a cada arranque, como root. Usa só curl e python3 (sem gcloud) com o token do
# servidor de metadados da conta de serviço da VM. Os marcadores @...@ são substituídos abaixo.
cat >"$WORK/startup.sh" <<'STARTUP'
#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
APP_DIR=/opt/onlinebusinesses
DATA_DIR=/var/lib/onlinebusinesses
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip ffmpeg git cron curl
timedatectl set-timezone Europe/Lisbon
# 1 GB de RAM chega mal para o ffmpeg: 2 GB de swap no disco.
if ! swapon --show | grep -q /swapfile; then
  [ -f /swapfile ] || { fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null; }
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
id onlinebusinesses >/dev/null 2>&1 || useradd --system --create-home --home-dir "$DATA_DIR" --shell /bin/bash onlinebusinesses
mkdir -p "$APP_DIR" "$DATA_DIR/out"
TOKEN="$(curl -sf -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
curl -sf -H "Authorization: Bearer $TOKEN" \
  "https://storage.googleapis.com/storage/v1/b/@DEPLOY_BUCKET@/o/app.tar.gz?alt=media" -o /tmp/app.tar.gz
tar -xzf /tmp/app.tar.gz -C "$APP_DIR"
rm -f /tmp/app.tar.gz
umask 077
curl -sf -H "Authorization: Bearer $TOKEN" \
  "https://secretmanager.googleapis.com/v1/projects/@PROJECT@/secrets/@SECRET@/versions/latest:access" |
  python3 -c 'import base64,json,sys; sys.stdout.write(base64.b64decode(json.load(sys.stdin)["payload"]["data"]).decode())' \
  >/etc/onlinebusinesses.env.new
install -m 600 -o onlinebusinesses -g onlinebusinesses /etc/onlinebusinesses.env.new /etc/onlinebusinesses.env
rm -f /etc/onlinebusinesses.env.new
chown -R onlinebusinesses:onlinebusinesses "$APP_DIR" "$DATA_DIR"
su - onlinebusinesses -c "cd $APP_DIR && { [ -d .venv ] || python3 -m venv .venv; } && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e ."
cat >/tmp/ob-crontab <<CRON
CRON_TZ=Europe/Lisbon
0 7 * * *   cd $APP_DIR && .venv/bin/python -m onlinebusinesses research >> $DATA_DIR/cron.log 2>&1
* * * * *   cd $APP_DIR && .venv/bin/python -m onlinebusinesses poll >> $DATA_DIR/cron.log 2>&1
* * * * *   cd $APP_DIR && .venv/bin/python -m onlinebusinesses publish >> $DATA_DIR/cron.log 2>&1
0 9 * * 1   cd $APP_DIR && .venv/bin/python -m onlinebusinesses report >> $DATA_DIR/cron.log 2>&1
CRON
crontab -u onlinebusinesses /tmp/ob-crontab
rm -f /tmp/ob-crontab
systemctl enable --now cron
STARTUP
sed -i -e "s|@DEPLOY_BUCKET@|$DEPLOY_BUCKET|g" -e "s|@PROJECT@|$GOOGLE_CLOUD_PROJECT|g" -e "s|@SECRET@|$SECRET|g" \
  "$WORK/startup.sh"

say "VM $VM (e2-micro, $ZONE, disco padrão de 30 GB: nível gratuito)"
if gcloud compute instances describe "$VM" --zone="$ZONE" >/dev/null 2>&1; then
  gcloud compute instances add-metadata "$VM" --zone="$ZONE" --metadata-from-file=startup-script="$WORK/startup.sh" >/dev/null
  gcloud compute instances reset "$VM" --zone="$ZONE" >/dev/null  # volta a correr o startup-script: código e segredos novos
  action="atualizada e reiniciada"
else
  gcloud compute instances create "$VM" --zone="$ZONE" --machine-type=e2-micro \
    --image-family=debian-12 --image-project=debian-cloud --boot-disk-size=30GB --boot-disk-type=pd-standard \
    --service-account="$SA_EMAIL" --scopes=cloud-platform --metadata-from-file=startup-script="$WORK/startup.sh" >/dev/null
  action="criada"
fi

configured() { if [ -n "${!1:-}" ]; then echo "sim"; else echo "não"; fi; }
say "Resumo"
cat <<SUMMARY
Projeto ............ $GOOGLE_CLOUD_PROJECT
VM ................. $VM ($ZONE, e2-micro) $action; o arranque demora alguns minutos
Bucket de vídeos ... gs://$GCS_BUCKET (público)
Bucket de código ... gs://$DEPLOY_BUCKET (privado)
Segredos ........... Secret Manager: $SECRET (nova versão); na VM: /etc/onlinebusinesses.env (modo 600)
Cron ............... research 07:00 (Lisboa); poll e publish cada minuto; report à segunda 09:00
Brave .............. $(configured BRAVE_API_KEY)
Instagram PT / ES .. $(configured INSTAGRAM_ACCESS_TOKEN) / $(configured INSTAGRAM_ACCESS_TOKEN_ES)
TikTok PT / ES ..... $(configured TIKTOK_ACCESS_TOKEN) / $(configured TIKTOK_ACCESS_TOKEN_ES)
Registo do arranque: gcloud compute instances get-serial-port-output $VM --zone=$ZONE
SUMMARY
