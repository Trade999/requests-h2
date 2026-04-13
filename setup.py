from setuptools import setup, find_packages

setup(
    name="requests-h2",
    version="1.0",
    author="Trade999",
    url="https://github.com/Trade999/requests-h2",
    description="Bibliothèque Python permettant d'utiliser facilement les requêtes HTTP/2 avec une interface proche de requests.",
    long_description="""
requests-h2 est une bibliothèque Python qui facilite l'utilisation du protocole HTTP/2
dans vos applications, avec une approche simple et pratique inspirée de requests.

Elle permet d'effectuer des requêtes HTTP tout en profitant des avantages de HTTP/2,
comme une meilleure gestion des connexions, des performances améliorées et une communication plus moderne.
""",
    long_description_content_type="text/plain",
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
        "urllib3>=1.26.0",
        "httpcore>=0.17.0",
        "certifi>=2023.0.0",
    ],
    extras_require={
        "brotli": [
            "brotli>=1.0.9; platform_python_implementation == 'CPython'",
            "brotlicffi>=1.0.9; platform_python_implementation != 'CPython'",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Natural Language :: French",
    ],
    keywords="http2 requests python networking client",
)