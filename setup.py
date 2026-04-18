from setuptools import setup

APP = ['pomobar.py']
OPTIONS = {
    'argv_emulation': False,
    'emulate_shell_environment': True,
    'iconfile': 'PomoBar.icns',
    'plist': {
        'CFBundleName': 'PomoBar',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,
    },
    'packages': ['rumps'],
    'frameworks': ['/opt/homebrew/opt/libffi/lib/libffi.8.dylib'],
}

setup(
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)