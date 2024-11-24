import logging

logging.basicConfig(level=logging.DEBUG)
import pyasyncio


async def start():
    print('hello world')


pyasyncio.run(start(), debug=True)
