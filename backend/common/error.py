"""
脚本说明：这个脚本放后端业务相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
class SingleMessageError(Exception):
    """
    类说明：SingleMessageError 表示后端业务过程里的特定错误，让上层能更准确地提示或处理。
    """
    def __init__(self, message):
        """
        是什么：SingleMessageError.__init__ 是 SingleMessageError 里的一个步骤，帮它完成后端业务相关的一件事。
        谁调用：创建 SingleMessageError 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        super().__init__(message)
        self.message = message

    def __str__(self):
        """
        是什么：SingleMessageError.__str__ 是 SingleMessageError 里的一个步骤，帮它完成后端业务相关的一件事。
        谁调用：Python 在需要这个特殊行为时会自动调用它。
        做了什么：把对象变成一段好读的文字，方便打印或看日志。
        """
        return self.message


class AppDBConnectionError(Exception):
    """
    类说明：AppDBConnectionError 表示后端业务过程里的特定错误，让上层能更准确地提示或处理。
    """
    pass


class AppDBError(Exception):
    """
    类说明：AppDBError 表示后端业务过程里的特定错误，让上层能更准确地提示或处理。
    """
    pass


class ParseSQLResultError(Exception):
    """
    类说明：ParseSQLResultError 表示后端业务过程里的特定错误，让上层能更准确地提示或处理。
    """
    pass
