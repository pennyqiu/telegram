#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AXA安盛产品收集器
智能爬取产品列表 + 半自动下载PDF

策略：
1. 慢速爬取产品列表（5-10秒间隔）
2. 提取产品信息和PDF链接
3. 人工确认后批量下载
4. 为AI分析准备结构化数据
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import os
from datetime import datetime
from urllib.parse import urljoin
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class AXAProductCollector:
    """AXA产品收集器"""
    
    def __init__(self):
        self.base_url = "https://www.axa.com.hk"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        
        # AXA产品类别
        self.categories = {
            'savings': {
                'name': '储蓄计划',
                'url': '/zh/our-products/savings',
                'keywords': ['储蓄', '保险', 'savings', 'insurance']
            },
            'protection': {
                'name': '医疗/危疾保障',
                'url': '/zh/our-products/health-protection',
                'keywords': ['医疗', '危疾', '保障', 'health', 'critical']
            },
            'life': {
                'name': '人寿保障',
                'url': '/zh/our-products/life-protection',
                'keywords': ['人寿', 'life']
            }
        }
        
        self.products = []
    
    def fetch_page(self, url, delay=5):
        """礼貌地获取页面"""
        try:
            logging.info(f"正在访问: {url}")
            time.sleep(delay)  # 礼貌性延迟
            
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            return response.text
        except Exception as e:
            logging.error(f"访问失败: {e}")
            return None
    
    def parse_product_page(self, html, category):
        """解析产品页面，提取产品信息"""
        soup = BeautifulSoup(html, 'html.parser')
        products = []
        
        # 这里需要根据AXA网站实际结构调整
        # 以下是通用的查找逻辑
        
        # 查找产品链接
        product_links = soup.find_all('a', href=True)
        
        for link in product_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # 过滤出可能是产品的链接
            if any(kw in text.lower() or kw in href.lower() 
                   for kw in category['keywords']):
                
                if href.startswith('/'):
                    href = urljoin(self.base_url, href)
                
                # 避免重复
                if href not in [p['url'] for p in products]:
                    products.append({
                        'name': text,
                        'url': href,
                        'category': category['name']
                    })
        
        return products
    
    def find_pdf_links(self, product_url, delay=5):
        """在产品页面查找PDF链接"""
        html = self.fetch_page(product_url, delay)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        pdf_links = []
        
        # 查找所有PDF链接
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if '.pdf' in href.lower() or 'pdf' in text.lower():
                if href.startswith('/'):
                    href = urljoin(self.base_url, href)
                
                # 识别PDF类型
                pdf_type = 'unknown'
                if any(kw in text.lower() for kw in ['说明书', 'brochure', '概要']):
                    pdf_type = 'brochure'
                elif any(kw in text.lower() for kw in ['条款', 'terms', 'policy']):
                    pdf_type = 'terms'
                elif any(kw in text.lower() for kw in ['单张', 'fact sheet']):
                    pdf_type = 'factsheet'
                
                pdf_links.append({
                    'url': href,
                    'text': text,
                    'type': pdf_type
                })
        
        return pdf_links
    
    def collect_all_products(self, delay=5):
        """收集所有产品信息"""
        logging.info("="*80)
        logging.info("开始收集AXA产品信息")
        logging.info(f"延迟设置: {delay}秒/页")
        logging.info("="*80)
        
        all_products = []
        
        for cat_id, category in self.categories.items():
            logging.info(f"\n正在收集类别: {category['name']}")
            
            url = urljoin(self.base_url, category['url'])
            html = self.fetch_page(url, delay)
            
            if html:
                products = self.parse_product_page(html, category)
                logging.info(f"找到 {len(products)} 个产品")
                all_products.extend(products)
            
            # 类别间额外延迟
            time.sleep(delay)
        
        self.products = all_products
        logging.info(f"\n总计找到 {len(all_products)} 个产品")
        
        return all_products
    
    def collect_pdf_links(self, delay=8):
        """为每个产品收集PDF链接"""
        logging.info("\n开始收集PDF链接...")
        
        for i, product in enumerate(self.products, 1):
            logging.info(f"\n[{i}/{len(self.products)}] {product['name']}")
            
            pdf_links = self.find_pdf_links(product['url'], delay)
            product['pdf_links'] = pdf_links
            
            if pdf_links:
                logging.info(f"  找到 {len(pdf_links)} 个PDF")
                for pdf in pdf_links:
                    logging.info(f"    - {pdf['text']} ({pdf['type']})")
            else:
                logging.info("  未找到PDF")
        
        return self.products
    
    def export_product_list(self, filename='axa_products.json'):
        """导出产品列表"""
        data = {
            'collect_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_products': len(self.products),
            'products': self.products
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logging.info(f"\n✅ 已导出产品列表: {filename}")
        
        # 同时生成下载列表
        self.generate_download_list()
    
    def generate_download_list(self, filename='axa_download_list.json'):
        """生成PDF下载列表（供pdf_downloader.py使用）"""
        download_list = []
        
        for product in self.products:
            if 'pdf_links' in product and product['pdf_links']:
                # 优先选择产品说明书
                brochures = [p for p in product['pdf_links'] if p['type'] == 'brochure']
                pdf_link = brochures[0] if brochures else product['pdf_links'][0]
                
                download_list.append({
                    'url': pdf_link['url'],
                    'company': 'AXA',
                    'product_name': product['name'],
                    'category': product['category'],
                    'pdf_type': pdf_link['type']
                })
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(download_list, f, ensure_ascii=False, indent=2)
        
        logging.info(f"✅ 已生成下载列表: {filename} ({len(download_list)}个PDF)")
        
        return download_list
    
    def interactive_collect(self):
        """交互式收集"""
        print("""
        ╔════════════════════════════════════════════════════════════════╗
        ║        AXA安盛产品收集器 v1.0                                 ║
        ║        智能爬取 + 人工确认 + 批量下载                          ║
        ╚════════════════════════════════════════════════════════════════╝
        
        工作流程：
        1. 慢速爬取产品列表（5-10秒/页）
        2. 提取每个产品的PDF链接
        3. 导出结构化数据
        4. 您确认后使用 pdf_downloader.py 批量下载
        
        预计用时：
        - 产品列表收集：5-10分钟
        - PDF链接收集：20-30分钟（根据产品数量）
        - 批量下载：10-15分钟
        
        ══════════════════════════════════════════════════════════════════
        """)
        
        delay = input("设置访问延迟（秒，建议5-10）[默认5]: ").strip()
        delay = int(delay) if delay else 5
        
        confirm = input(f"\n确认开始收集？延迟={delay}秒 (y/n): ").strip().lower()
        
        if confirm != 'y':
            print("已取消")
            return
        
        # 步骤1：收集产品列表
        print("\n" + "="*80)
        print("步骤 1/3: 收集产品列表")
        print("="*80)
        self.collect_all_products(delay)
        
        if not self.products:
            print("❌ 未找到产品，可能需要调整爬取逻辑")
            return
        
        # 显示产品列表
        print(f"\n找到以下产品：")
        for i, product in enumerate(self.products[:10], 1):
            print(f"  {i}. {product['name']} ({product['category']})")
        if len(self.products) > 10:
            print(f"  ... 还有 {len(self.products) - 10} 个产品")
        
        # 步骤2：收集PDF链接
        collect_pdf = input(f"\n继续收集PDF链接？(y/n): ").strip().lower()
        
        if collect_pdf == 'y':
            print("\n" + "="*80)
            print("步骤 2/3: 收集PDF链接")
            print("="*80)
            
            pdf_delay = input(f"PDF收集延迟（秒，建议8-10）[默认{delay+3}]: ").strip()
            pdf_delay = int(pdf_delay) if pdf_delay else delay + 3
            
            self.collect_pdf_links(pdf_delay)
        
        # 步骤3：导出数据
        print("\n" + "="*80)
        print("步骤 3/3: 导出数据")
        print("="*80)
        self.export_product_list()
        
        print("""
        ══════════════════════════════════════════════════════════════════
        ✅ 收集完成！
        
        生成的文件：
        1. axa_products.json - 完整产品信息（供AI分析）
        2. axa_download_list.json - PDF下载列表
        
        下一步：
        1. 检查 axa_download_list.json，确认PDF链接
        2. 运行: python3 pdf_downloader.py
        3. 选择功能2，使用 axa_download_list.json 批量下载
        4. 下载完成后，运行 AI 分析工具
        
        ══════════════════════════════════════════════════════════════════
        """)


def manual_mode():
    """手动模式：提供常用产品的直接链接"""
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║        AXA热门产品快速收集                                     ║
    ╚════════════════════════════════════════════════════════════════╝
    
    以下是AXA的热门产品列表，您可以直接访问：
    """)
    
    hot_products = [
        {
            'name': '盛利II储蓄保险 - 至尊版',
            'url': 'https://www.axa.com.hk/zh/wealth-ahead-ii-savings-insurance-supreme',
            'category': '储蓄计划'
        },
        {
            'name': '盛利II储蓄保险 - 优越版',
            'url': 'https://www.axa.com.hk/zh/wealth-ahead-ii-savings-insurance-plus',
            'category': '储蓄计划'
        },
        {
            'name': '安进储蓄保险',
            'url': 'https://www.axa.com.hk/zh/wealth-compass-savings-insurance',
            'category': '储蓄计划'
        },
        {
            'name': '挚爱保危疾保险',
            'url': 'https://www.axa.com.hk/zh/emma-critical-illness-protector',
            'category': '危疾保障'
        },
        {
            'name': '康誉医疗保险',
            'url': 'https://www.axa.com.hk/zh/wealth-prestige-medical-insurance',
            'category': '医疗保障'
        }
    ]
    
    for i, product in enumerate(hot_products, 1):
        print(f"\n{i}. {product['name']}")
        print(f"   类别: {product['category']}")
        print(f"   链接: {product['url']}")
    
    print("""
    
    手动操作步骤：
    1. 访问上述链接
    2. 在产品页面找到"产品说明书"或"下载"按钮
    3. 右键复制PDF链接
    4. 填写到 download_list.json
    5. 使用 pdf_downloader.py 批量下载
    """)


def main():
    print("""
    AXA产品收集器
    
    模式选择：
    1. 自动收集模式 - 智能爬取全部产品（推荐）
    2. 手动收集模式 - 提供热门产品链接
    0. 退出
    """)
    
    choice = input("请选择模式 (0-2): ").strip()
    
    if choice == '1':
        collector = AXAProductCollector()
        collector.interactive_collect()
    elif choice == '2':
        manual_mode()
    else:
        print("退出")


if __name__ == '__main__':
    main()
