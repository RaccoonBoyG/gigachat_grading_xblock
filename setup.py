from setuptools import setup, find_packages
import os
from pip.req import parse_requirements


def package_data(pkg, roots):
    """Generic function to find package_data.

    All of the files under each of the `roots` will be declared as package
    data for package `pkg`.

    """
    data = []
    for root in roots:
        for dirname, _, files in os.walk(os.path.join(pkg, root)):
            for fname in files:
                data.append(os.path.relpath(os.path.join(dirname, fname), pkg))

    return {pkg: data}

# parse_requirements() returns generator of pip.req.InstallRequirement objects
install_reqs = parse_requirements('./requirements.txt')

# reqs is a list of requirement
# e.g. ['django==1.5.1', 'mezzanine==1.4.6']
reqs = [str(ir.req) for ir in install_reqs]


setup(
    name='gigachat_grading_xblock',
    version='0.1',
    description='XBlock для проверки работ с помощью gigachat API',
    packages=find_packages(),
    install_requires=[
        'gigachat',
        'PyPDF2',
        'python-docx',
        'XBlock'
        # другие зависимости, если нужны
    ],
    entry_points={
        'xblock.v1': [
            'gigachat_grading_xblock = gigachat_grading_xblock.grading:GigaChatAIGradingXBlock',
        ]
    },
    package_data=package_data("gigachat_grading_xblock", ["static", "public"]),
)
