from pprint import pprint
from textwrap import wrap
from flask import Flask, jsonify, request

app = Flask(__name__)
methods = ["GET", "POST", "PATCH", "DELETE"]


@app.route("/", methods=methods, defaults={"path": ""})
@app.route("/<path:path>", methods=methods)
def hello_world(path):
    return 'hello world'


if __name__ == "__main__":
    app.run(host='0.0.0.0')
