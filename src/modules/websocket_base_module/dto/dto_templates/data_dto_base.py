class BaseDataTransferObject:
    """
    DTO基类
    子类按需重写成员函数即可
    """
    def __init__(self):
        pass
    def to_json(self):
        """
        将DTO对象转换为JSON
        """
        pass
    def from_json(self, json_data):
        """
        从JSON数据中创建DTO对象
        """
        pass
    def to_binary(self):
        """
        将DTO对象转换为二进制
        """
        pass
    def from_binary(self, binary_data):
        """
        从二进制数据中创建DTO对象
        """
        pass
    def to_text(self):
        """
        将DTO对象转换为文本
        """
        pass
    def from_text(self, text_data):
        """
        从文本数据中创建DTO对象
        """
        pass