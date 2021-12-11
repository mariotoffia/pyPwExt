from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()

long_description = (here / 'README.md').read_text(encoding='utf-8')
VERSION = (here / 'RELEASE-VERSION.txt').read_text(encoding='utf-8')[:-1]

if not VERSION:
    raise ValueError("Unable to get version from git")

setup(
    name='pypwext',
    python_requires='>=3.8, <4',
    package_dir={"": "pypwext"},
    packages=find_packages(where="pypwext"),
    version=VERSION,
    license='APACHE 2.0',
    author='Mario Toffia',
    author_email='mario.toffia@example.com',
    maintainer='Mario Toffia',
    maintainer_email='mario.toffia@example.com',
    description='Extension and Decorator for the AWS Lambda Powertools Library',
    long_description=long_description,
    long_description_content_type='text/markdown',
    project_urls={
        'Source': 'https://github.com/mariotoffia/pypwext',
        'Documentation': 'https://github.com/mariotoffia/pypwext',
        'Tracker': 'https://github.com/mariotoffia/pypwext/issues',
    },
    download_url=f'https://github.com/mariotoffia/pypwext/archive/refs/tags/{VERSION}.tar.gz',
    url='https://github.com/mariotoffia/pypwext',
    install_requires=[
        'chardet'
        'aws-requests-auth',
        'aws-lambda-powertools',
        'boto3',
        'botocore',
        'email-validator',
        'pydantic'
    ],
    keywords=['AWS', 'Lambda', 'Library', 'Decorator'],
    classifiers=[
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        "Programming Language :: Python :: 3",  # "3 - Alpha", "4 - Beta" or "5 - Production/Stable"
        "License :: OSI Approved :: MIT License",
        'License :: OSI Approved :: Apache Software License',
        "Operating System :: OS Independent",
    ],
)
