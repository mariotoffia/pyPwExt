from distutils.core import setup
setup(
    name='pypwext',
    packages=['pypwext'],
    version='0.1',
    license='APACHE 2.0',
    description='Extension and Decorator for the AWS Lambda Powertools Library',
    author='Mario Toffia',
    author_email='mario.toffia@domain.com',
    url='https://github.com/mariotoffia/pypwext',
    download_url='https://github.com/mariotoffia/pypwext/archive/refs/tags/v_01.tar.gz',
    keywords=['AWS', 'Lambda', 'Library', 'Decorator'],
    install_requires=[
        'chardet'
        'aws-requests-auth',
        'aws-lambda-powertools',
        'boto3',
        'botocore',
        'email-validator',
        'pydantic'
    ],
    classifiers=[
        'Development Status :: 4 - Beta',      # "3 - Alpha", "4 - Beta" or "5 - Production/Stable"
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: APACHE 2.0 License',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
)
