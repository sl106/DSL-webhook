import logging
import yaml
from DSL.data.utils import DSL


dsl = DSL()
data = {}


def load():
    """
    load yml config files
    """
    global data
    try:
        with open("DSL.yaml") as file:
            data = yaml.load(file, Loader=yaml.FullLoader)
            logging.info("opening yml config file {}" "".format("DSL.yml"))
    except Exception as e:
        logging.critical(
            "Cannot read yaml config file {}, check formatting." "".format("DSL.yml")
        )


def parseData():
    global data
    for item in data:
        if "group" in item:
            method_to_call = getattr(dsl, item["group"])
            method_to_call(item)
        if "action" in item:
            method_to_call = getattr(dsl, item["action"])
            method_to_call(item)


def main():
    logging.basicConfig(level=logging.INFO)
    load()
    parseData()


if __name__ == "__main__":
    main()
