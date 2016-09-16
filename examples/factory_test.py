import env
import random
from nida.util.factory import Factory


class Father(Factory):

    def __init__(self, some_arg):
        self.some_arg = some_arg

    @classmethod
    def config_base(cls):
        return Father

    @classmethod
    def config_sub(cls):
        rand = random.randint(0,9)
        return Child1 if rand < 5 else Child2

class Child1(Father):
    pass

class Child2(Father):
    pass

if __name__ == "__main__":
    f = Father(2)
    print type(f)
    print f.some_arg
