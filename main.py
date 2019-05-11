from Machine import Machine
from argparse import ArgumentParser
import logging
import json


def parse_arguments():
    parser = ArgumentParser()
    parser.add_argument("branch", help="remote branch from which changes will be pulled")
    parser.add_argument("-d", "--debug", '--DEBUG', action='store_true', help="set logging to be debug")
    return parser.parse_args()


def test(machine_info, constants, branch):
    machine = Machine(machine_info, constants)
    machine.initialize()
    initial_branch = machine.get_active_branch()
    branch_created_flag = False
    if not machine.switch_branch(branch):
        branch_created_flag = machine.create_branch(branch)
        machine.switch_branch(branch)
    machine.pull_changes_from_remote_branch(branch)
    machine.build_application()
    machine.copy_log_to_log_dir()
    machine.switch_branch(initial_branch)
    if branch_created_flag:
        machine.remove_branch(branch)
    machine.power_down_virtual_machine()
    return True


def main():
    args = parse_arguments()
    if args.debug:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO
    logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(message)s', datefmt='%H:%M:%S', level=loglevel)
    logging.info('Starting building and testing script')

    with open("config.json", "r") as read_file:
        data = json.load(read_file)

    results = []
    for machineInfo in data['machine']:
        results.append(test(machineInfo, data['constants'], args.branch))

    if False in results:
        logging.info('Failed')
    else:
        logging.info("Success")


if __name__ == "__main__":
    main()
