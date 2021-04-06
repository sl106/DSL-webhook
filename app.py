import yaml
from flask import Flask
from flask import request
import logging
import DSL.main as dsl
app = Flask(__name__)


# Start ngrok when app is run


@app.route('/')
def hello_world():
    return 'Hello World!'


@app.route('/push', methods=['POST'])
def push_event():
    data = []
    result = request.json
    print(request.json)
    project_id = result['project_id']
    # fork project
    data.append({'action': 'fork_project','var':'fork',
                 'attributes': {'id': project_id, 'namespace_id': 342, 'visibility': 'private'}})
    data.append({'action': 'create_commit',
                 'attributes': {'branch': 'master',
                                'commit_message': 'add test file and ci yml file',
                                'file': 'tests.py, .gitlab-ci.yml',
                                'file_path': 'resource/tests.py, resource/.gitlab-ci.yml'},
                 'to': 'fork'})
    try:
        with open('DSL.yaml', "w") as file:
            yaml.dump(data, file)
    except Exception as e:
        logging.error('cannot open file')
    dsl.main()
    return 'i got this'


if __name__ == '__main__':
    app.run()
