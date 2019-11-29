import logging
import os
import connexion
from Flask_AuditLog import AuditLog
from Flask_No_Cache import CacheControl
from flask_cors import CORS
from flask_sslify import SSLify

app = connexion.App(__name__, specification_dir='./openapi_server/openapi/')
app.add_api('openapi.yaml',
            arguments={'title': 'nssurveyapi'},
            pythonic_params=True)
CORS(app.app)

logging.basicConfig(level=logging.INFO)

AuditLog(app)
CacheControl(app)
if 'GAE_INSTANCE' in os.environ:
    SSLify(app.app, permanent=True)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)
