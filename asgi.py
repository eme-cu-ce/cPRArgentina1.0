import os
import sys


project_home = "/home/cprargentina/pra_hla_argentina"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ["CPRA_DB"] = "cpra.db"

from main import app
