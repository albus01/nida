"""
author: shawnsha@tencent.com
date: 2016.08.11

Static Factory to generate submodule.
"""

class Factory(object):
    def __new__(cls, *args, **kwargs):
        base = cls.config_base()
        if base is cls:
            impl = cls.config_sub()
        else:
            impl = cls

        instance = super(Factory, cls).__new__(impl)

        instance.__init__(*args, **kwargs)

        return instance

    def config_base():
        raise NotImplementedError()

    def config_sub():
        raise NotImplementedError()

