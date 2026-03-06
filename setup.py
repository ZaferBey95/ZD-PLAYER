from setuptools import setup, find_packages

setup(
    name="com.zdplayer",
    version="1.0",
    description="ZD PLAYER - IPTV Player",
    author="Zafer Demir",
    author_email="zfrdmr@protonmail.com",
    license="GPL-3.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    package_data={"zdplayer": ["logo.png"]},
    python_requires=">=3.10",
    install_requires=["requests"],
    entry_points={
        "console_scripts": [
            "zdplayer=zdplayer.app:main",
        ],
    },
)
