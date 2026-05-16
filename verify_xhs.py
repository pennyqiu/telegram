# -*- coding: utf-8 -*-
import io, os, re

print("========== 最终验证 ==========\n")

print("--- 文章文件 ---")
files = sorted([f for f in os.listdir("insurance-guide/articles") if f.startswith("v22-xhs")])
print(f"共 {len(files)} 个文件\n")

print("--- 链接完整性检查 ---")
broken = 0
for f in files:
    if not f.endswith(".html"):
        continue
    p = f"insurance-guide/articles/{f}"
    c = io.open(p, encoding="utf-8").read()
    for m in re.finditer(r'href=["\'](v22-xhs[\w-]*\.html)["\']', c):
        target = m.group(1)
        target_path = f"insurance-guide/articles/{target}"
        if not os.path.exists(target_path):
            print(f"  ✗ {f} -> {target} 不存在")
            broken += 1
print(f"  断链数: {broken}\n")

print("--- index.html 关键链接 ---")
content = io.open("insurance-guide/index.html", encoding="utf-8").read()
for kw in ["v22-xhs-hub", "v22-xhs01.html", "39 篇内容已 100% 完成上线", "小红书 39 篇日历"]:
    print(f"  '{kw}': {content.count(kw)} 处")

print("\n--- hub 页面文章列表完整性 ---")
hub = io.open("insurance-guide/articles/v22-xhs-hub.html", encoding="utf-8").read()
hub_links = re.findall(r'href="(v22-xhs\d{2}\.html)"', hub)
print(f"  hub 页中文章链接: {len(hub_links)} 个")
print(f"  唯一: {len(set(hub_links))} 个")
expected = set(f"v22-xhs{i:02d}.html" for i in range(1, 40))
missing = expected - set(hub_links)
extra = set(hub_links) - expected
print(f"  缺失: {missing or '无'}")
print(f"  多余: {extra or '无'}")

print("\n--- 文件大小汇总 ---")
total = sum(os.path.getsize(f"insurance-guide/articles/{f}") for f in files)
print(f"  全部小红书相关文件总大小: {total/1024:.1f} KB")
avg = total / len(files)
print(f"  平均每文件: {avg/1024:.1f} KB")

print("\n========== 全部验证完成 ==========")
