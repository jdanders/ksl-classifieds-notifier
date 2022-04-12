import logging
import json


def save_dict(file, d):
    logging.info("Saving file {file}".format(file=file))
    with open(file, 'w') as f:
        json.dump(d, f, indent=2)


def load_dict(file):
    logging.info("Loading file {file}".format(file=file))
    with open(file, 'r') as f:
        return json.load(f)