class SingleMessageError(Exception):
    def __init__(self, message):
        """
        是什么：SingleMessageError.__init__ 是 backend/common/error.py 中的同步方法。
        谁调用：由创建 SingleMessageError 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        super().__init__(message)
        self.message = message

    def __str__(self):
        """
        是什么：SingleMessageError.__str__ 是 backend/common/error.py 中的同步方法。
        谁调用：由 Python 运行时、框架协议或相关内置操作按需调用。
        做了什么：生成对象的文本表示，便于日志、调试或展示。
        """
        return self.message


class AppDBConnectionError(Exception):
    pass


class AppDBError(Exception):
    pass


class ParseSQLResultError(Exception):
    pass
