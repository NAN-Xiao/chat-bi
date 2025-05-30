import yaml

base_template = None


def load():
    with open('./template.yaml', 'r') as f:
        global base_template
        base_template = yaml.load(f, Loader=yaml.SafeLoader)


def get_base_template():
    if not base_template:
        load()
    return base_template
