def simple_generator():
    """
    一个简单生成器
    :return:
    """
    yield 1
    yield 2
    yield 3


def delegating_generator1():
    g = simple_generator()

    # 基于简单生成器造一个生成器，不断从简单生成器中yield数据
    try:
        while True:
            yield g.send(None)
    except StopIteration as e:
        ...


for value in delegating_generator1():
    print(value)


def delegating_generator2():
    g = simple_generator()
    # 基于简单生成器造一个生成器，使用 yield from 从另一个生成器中获取值
    yield from g


for value in delegating_generator2():
    print(value)
