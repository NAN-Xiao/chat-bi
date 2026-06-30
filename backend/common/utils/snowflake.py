"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import time
import threading
class SnowflakeGenerator:
    """
    类说明：SnowflakeGenerator 把通用工具相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def __init__(self, worker_id=0, datacenter_id=0):
        """
        是什么：SnowflakeGenerator.__init__ 是 SnowflakeGenerator 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：创建 SnowflakeGenerator 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.worker_id = worker_id
        self.datacenter_id = datacenter_id
        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()

        self.worker_id_bits = 5
        self.datacenter_id_bits = 5
        self.max_worker_id = -1 ^ (-1 << self.worker_id_bits)
        self.max_datacenter_id = -1 ^ (-1 << self.datacenter_id_bits)
        self.sequence_bits = 12

        self.worker_id_shift = self.sequence_bits
        self.datacenter_id_shift = self.sequence_bits + self.worker_id_bits
        self.timestamp_left_shift = self.sequence_bits + self.worker_id_bits + self.datacenter_id_bits
        self.sequence_mask = -1 ^ (-1 << self.sequence_bits)

        if self.worker_id > self.max_worker_id or self.worker_id < 0:
            raise ValueError(f"worker ID can't be greater than {self.max_worker_id} or less than 0")
        if self.datacenter_id > self.max_datacenter_id or self.datacenter_id < 0:
            raise ValueError(f"datacenter ID can't be greater than {self.max_datacenter_id} or less than 0")

    def _current_time(self):
        """
        是什么：SnowflakeGenerator._current_time 是 SnowflakeGenerator 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：拿到 SnowflakeGenerator 对象的代码，需要完成这个动作时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return int(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp):
        """
        是什么：SnowflakeGenerator._wait_next_millis 是 SnowflakeGenerator 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：拿到 SnowflakeGenerator 对象的代码，需要完成这个动作时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        timestamp = self._current_time()
        while timestamp <= last_timestamp:
            timestamp = self._current_time()
        return timestamp

    def generate_id(self):
        """
        是什么：SnowflakeGenerator.generate_id 是 SnowflakeGenerator 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：拿到 SnowflakeGenerator 对象的代码，需要完成这个动作时会调用它。
        做了什么：根据已有信息生成通用工具的结果，比如答案、SQL、图表或建议。
        """
        with self.lock:
            timestamp = self._current_time()

            if timestamp < self.last_timestamp:
                raise ValueError("Clock moved backwards. Refusing to generate ID")

            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.sequence_mask
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                self.sequence = 0

            self.last_timestamp = timestamp

            return ((timestamp << self.timestamp_left_shift) |
                    (self.datacenter_id << self.datacenter_id_shift) |
                    (self.worker_id << self.worker_id_shift) |
                    self.sequence)

snowflake = SnowflakeGenerator(worker_id=1)