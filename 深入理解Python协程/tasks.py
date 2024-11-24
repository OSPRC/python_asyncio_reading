from time import sleep

def task():
    print(f"enter {task.__name__}")
    sub_task_1()
    sub_task_2()
    print(f"exit {task.__name__}")


def sub_task_1():
    print(f"\tenter {sub_task_1.__name__}")
    data = sub_task_11()
    sub_task_12(data)
    print(f"\texit {sub_task_1.__name__}")


def sub_task_2():
    print(f"\tenter {sub_task_2.__name__}")
    sub_task_21()
    sub_task_22()
    print(f"\texit {sub_task_2.__name__}")


def sub_task_11():
    print(f"\t\tenter {sub_task_11.__name__}")
    print(f"\t\texit {sub_task_11.__name__}")


def sub_task_12(data):
    print(f"\t\tenter {sub_task_12.__name__}")
    print(f"\t\texit {sub_task_12.__name__}")


def sub_task_21():
    print(f"\t\tenter {sub_task_21.__name__}")
    sleep(3)
    print(f"\t\texit {sub_task_21.__name__}")


def sub_task_22():
    print(f"\t\tenter {sub_task_22.__name__}")
    print(f"\t\texit {sub_task_22.__name__}")


if __name__ == '__main__':
    task()
