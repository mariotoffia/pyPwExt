# -*- coding: utf-8 -*-
# Author: Douglas Creager <dcreager@dcreager.net>
# This file is placed into the public domain.
from subprocess import Popen, PIPE


def write_release_version(version):
    f = open("README.rst", "w")
    f.write("%s\n" % version)
    f.close()


def get_latest_tag_version():
    git = Popen(['git', 'describe', '--abbrev=0', '--tags'],
                stdout=PIPE, stderr=PIPE)

    git.stderr.close()
    lines = git.stdout.readlines()

    if len(lines) == 0:
        raise Exception('No tag found')

    line = lines[0].decode('utf-8').strip()
    write_release_version(line)


if __name__ == "__main__":
    get_latest_tag_version()
