from setuptools import setup, find_packages

setup(
    name="ken-agent",
    version="2.3.5",
    description="KEN AGENT - Autonomous Desktop AI Runner (HPD Ecosystem)",
    long_description=open("README.md", "r", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Do Thanh Tan",
    author_email="icoquangninh@gmail.com",
    url="https://api.haiphongdeveloper.com",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "websockets>=11.0",
    ],
    entry_points={
        "console_scripts": [
            "ken-agent=ken_agent.cli:main",
        ],
    },
)
