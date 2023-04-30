# ChromeDump

ChromeDump is a small tool to dump all JavaScript and other ressources going through the browser. It can be used to help JavaScript deobfuscation by catching every parser calls to V8. It is compatible with any browser supporting Chrome Devtools Protocol (CDP). It can be used along with PlayWright or Selenium. 

# Setup

## Debian

### install
```bash
apt install chromium zip python3 python3-pip
pip3 install -r requirements.txt
```
### run
```bash
python3 chromedump.py
```
