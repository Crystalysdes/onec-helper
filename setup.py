from setuptools import setup, find_packages

setup(
    name="onec-helper",
    version="1.0.0",
    packages=find_packages(include=["backend", "backend.*", "bot", "bot.*"]),
)
