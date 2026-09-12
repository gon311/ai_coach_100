import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from rag_index_contract import validate_index

class IndexContractTests(unittest.TestCase):
    def test_same_count_different_ids_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = root/'source.sqlite'
            db.write_bytes(b'fixture')
            (root/'BUILD_COMPLETE.json').write_text(json.dumps({
                'embedding_model':'jhgan/ko-sroberta-multitask',
                'source_database_sha256':hashlib.sha256(b'fixture').hexdigest()}))
            class Collection:
                def count(self): return 1
                def get(self, **kwargs): return {'ids':['unexpected']}
            with self.assertRaisesRegex(RuntimeError,'ID'):
                validate_index(db,root,Collection(),{'expected'})
            validate_index(db,root,Collection(),{'unexpected'})
            db.write_bytes(b'changed source with the same number of rows')
            with self.assertRaisesRegex(RuntimeError,'버전'):
                validate_index(db,root,Collection(),{'unexpected'})

if __name__ == '__main__':
    unittest.main()
