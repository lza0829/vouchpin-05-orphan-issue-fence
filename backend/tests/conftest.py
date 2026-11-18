"""隔离测试数据：必须在 app.config 被导入前指定独立 DATA_DIR。"""
import os
import tempfile

_test_data = tempfile.mkdtemp(prefix="vouchpin-test-")
os.environ["DATA_DIR"] = _test_data
