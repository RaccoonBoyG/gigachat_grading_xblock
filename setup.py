from setuptools import setup, find_packages
import os
import re


def get_version(*file_paths):
    """
    Extract the version string from the file at the given relative path fragments.
    """
    filename = os.path.join(os.path.dirname(__file__), *file_paths)
    version_file = open(filename).read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)

    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


def package_data(pkg, roots):
    """
    Generic function to find package_data.

    All of the files under each of the `roots` will be declared as a package
    data for package `pkg`.
    """
    data = []
    for root in roots:
        for dirname, _, files in os.walk(os.path.join(pkg, root)):
            for fname in files:
                data.append(os.path.relpath(os.path.join(dirname, fname), pkg))

    return {pkg: data}

VERSION = get_version("gigachat_grading_xblock", "__init__.py")

with open('requirements.txt') as f:
    required = f.read().splitlines()

setup(
    name='gigachat_grading_xblock',
    version=VERSION,
    description='XBlock для проверки работ с помощью gigachat API',
    packages=[
        "gigachat_grading_xblock",
    ],
    install_requires=required,
    entry_points={
        'xblock.v1': [
            'gigachat_grading_xblock = gigachat_grading_xblock:GigaChatAIGradingXBlock',
        ]
    },
    package_data=package_data("gigachat_grading_xblock", ["static", "public"]),
)
