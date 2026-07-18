from setuptools import setup, find_packages

setup(
    name='yt-skill-generator',
    version='0.1.0',
    description='A generalized YouTube skill extraction tool with a TUI.',
    author='Antigravity',
    packages=find_packages(),
    install_requires=[
        'httpx',
        'python-dotenv',
        'prompt_toolkit',
        'youtube-transcript-api',
        'yt-dlp',
        'pyyaml',
        'google-api-python-client',
        'pydantic',
        'google-genai',
        'GitPython',
        'rich'
    ],
    entry_points={
        'console_scripts': [
            'yt-skill-generator = yt_skill_generator.main:main'
        ]
    }
)
