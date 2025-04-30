#!/usr/bin/env python3
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = f.read().splitlines()

setup(
    name="securetermchat",
    version="0.1.0",
    author="SecureTermChat Team",
    author_email="author@example.com",
    description="Анонимный защищенный P2P мессенджер для терминала",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/username/securetermchat",
    packages=find_packages(),
    classifiers=[
        "Язык программирования :: Python :: 3",
        "Лицензия :: OSI Approved :: MIT License",
        "Операционная система :: OS Independent",
        "Статус разработки :: 3 - Alpha",
        "Окружение :: Консоль",
        "Тема :: Коммуникации :: Чат",
        "Тема :: Безопасность :: Криптография",
    ],
    python_requires=">=3.7",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "securetermchat=securetermchat:main",
        ],
    },
) 