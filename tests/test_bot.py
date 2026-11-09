import sys, os, time, json, logging, urllib.request
sys.path.insert(0, os.getcwd())
logging.basicConfig(level=logging.WARNING)
from pf_bot import bot
req = urllib.request.Request('http://localhost:8082/api/auth/login', data=json.dumps({"email": "smoketest.redesign@example.com", "password": "Test@12345"}).encode(), headers={'Content-Type': 'application/json'})
d = json.loads(urllib.request.urlopen(req).read())['data']; jwt = d.get('token') or d.get('accessToken')
state, history = {}, []
QS = sys.argv[1:] or ["Shop có giày Nike size 42 không?", "còn size 44 không", "Phí ship về Hà Nội bao nhiêu?",
      "Có mã giảm giá nào đang chạy không?", "Giày chạy bộ nào dưới 2 triệu?", "Chính sách đổi trả thế nào?",
      "chân mình dài 26cm thì đi size nào", "đơn hàng của mình giao chưa", "hủy đơn ORD-AD5BBCE0", "hôm nay trời đẹp không",
      "shop có bán hàng chính hãng không"]
for q in QS:
    t = time.time(); first = None; text = ""; prods = []
    for ev in bot.respond(q, history, jwt, state):
        if ev["type"] == "delta":
            first = first or time.time() - t; text += ev["text"]
        elif ev["type"] == "products":
            prods = ev["items"]
    dt = time.time() - t
    print(f"\n### {q}   [first {first or 0:.1f}s / total {dt:.1f}s]\n{text.strip()}")
    for p in prods: print(f"   • {p['name']} · {p['price']:,} · sizes {p['sizesInStock'][:8]} · stock@size {p.get('sizeStock')}")
    history += [{"role": "user", "content": q}, {"role": "bot", "content": text}]
