import subprocess,unittest
class Smoke(unittest.TestCase):
 def test_demo(self):
  p=subprocess.run(['bin/autoresearch','smoke'],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
if __name__=='__main__': unittest.main()
