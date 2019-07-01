import connexion
from flask_cors import CORS

app = connexion.App(__name__, specification_dir='./openapi_server/openapi/')
app.add_api('openapi.yaml',
            arguments={'title': 'nssurveyapi'},
            pythonic_params=True)
CORS(app.app)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)
