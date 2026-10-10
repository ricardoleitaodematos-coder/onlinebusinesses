import os
import sys

from .cli import load_env_file, main

raise SystemExit(main(sys.argv[1:], load_env_file(os.environ)))
