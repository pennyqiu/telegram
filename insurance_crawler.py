#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
保险产品信息收集工具（仅供个人学习研究使用）
使用前请确保：
1. 遵守网站 robots.txt 规则
2. 设置合理的请求间隔
3. 仅用于个人学习，不用于商业目的
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import pandas as pd
from datetime import datetime
import os
from urllib.parse import urljoin, urlparse
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('insurance_crawler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class InsuranceCrawler:
    """保险产品信息收集器"""
    
    def __init__(self, output_dir='insurance_data'):
        self.output_dir = output_dir
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        for company in ['平安', '人寿', 'AXA', 'Prudential']:
            os.makedirs(os.path.join(output_dir, company), exist_ok=True)
    
    def check_robots_txt(self, base_url):
        """检查网站的 robots.txt"""
        try:
            robots_url = urljoin(base_url, '/robots.txt')
            response = self.session.get(robots_url, timeout=10)
            if response.status_code == 200:
                logging.info(f"Robots.txt 内容:\n{response.text[:500]}")
                return response.text
            else:
                logging.warning(f"无法访问 robots.txt: {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"检查 robots.txt 时出错: {e}")
            return None
    
    def fetch_page(self, url, delay=3):
        """获取网页内容，带延迟"""
        try:
            logging.info(f"正在访问: {url}")
            time.sleep(delay)  # 尊重服务器，避免频繁请求
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            return response.text
        except requests.RequestException as e:
            logging.error(f"访问 {url} 失败: {e}")
            return None
    
    def save_product_info(self, company, product_name, data):
        """保存产品信息"""
        filename = f"{company}/{product_name}_{datetime.now().strftime('%Y%m%d')}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logging.info(f"已保存: {filepath}")
    
    def crawl_pingan(self):
        """平安保险产品列表（示例框架）"""
        logging.info("=" * 50)
        logging.info("开始收集平安保险产品信息")
        logging.info("=" * 50)
        
        base_url = "https://www.pingan.com/official/lifeinsurance"
        
        # 检查 robots.txt
        self.check_robots_txt("https://www.pingan.com")
        
        # 这里需要根据实际网站结构调整
        # 以下是示例框架
        products = []
        
        logging.info("提示：需要手动分析网站结构来提取产品信息")
        logging.info(f"建议访问: {base_url}")
        
        return products
    
    def crawl_chinalife(self):
        """中国人寿产品列表（示例框架）"""
        logging.info("=" * 50)
        logging.info("开始收集中国人寿产品信息")
        logging.info("=" * 50)
        
        base_url = "http://www.chinalife.com.cn/chinalife/cpzx17/insurance/"
        
        self.check_robots_txt("http://www.chinalife.com.cn")
        
        logging.info("提示：需要手动分析网站结构来提取产品信息")
        logging.info(f"建议访问: {base_url}")
        
        return []
    
    def crawl_axa_hk(self):
        """AXA香港产品列表（示例框架）"""
        logging.info("=" * 50)
        logging.info("开始收集AXA香港产品信息")
        logging.info("=" * 50)
        
        base_url = "https://www.axa.com.hk/zh"
        
        self.check_robots_txt("https://www.axa.com.hk")
        
        logging.info("提示：需要手动分析网站结构来提取产品信息")
        logging.info(f"建议访问: {base_url}")
        
        return []
    
    def crawl_prudential_hk(self):
        """保诚香港产品列表（示例框架）"""
        logging.info("=" * 50)
        logging.info("开始收集保诚香港产品信息")
        logging.info("=" * 50)
        
        base_url = "https://www.prudential.com.hk/sc/"
        
        self.check_robots_txt("https://www.prudential.com.hk")
        
        logging.info("提示：需要手动分析网站结构来提取产品信息")
        logging.info(f"建议访问: {base_url}")
        
        return []
    
    def export_to_excel(self, all_products):
        """导出到Excel进行对比"""
        if not all_products:
            logging.warning("没有产品数据可导出")
            return
        
        df = pd.DataFrame(all_products)
        excel_path = os.path.join(self.output_dir, f'保险产品对比_{datetime.now().strftime("%Y%m%d")}.xlsx')
        df.to_excel(excel_path, index=False, engine='openpyxl')
        logging.info(f"已导出Excel文件: {excel_path}")


def main():
    """主函数"""
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║           保险产品信息收集工具 v1.0                            ║
    ║           仅供个人学习研究使用                                  ║
    ╚════════════════════════════════════════════════════════════════╝
    
    重要提示：
    1. 本工具仅作为技术学习框架
    2. 实际使用前请确认遵守各网站的服务条款
    3. 建议通过官方渠道获取完整产品资料
    4. 保险产品信息经常更新，请以官网最新信息为准
    """)
    
    crawler = InsuranceCrawler()
    
    print("\n可用选项:")
    print("1. 收集平安保险产品信息")
    print("2. 收集中国人寿产品信息")
    print("3. 收集AXA香港产品信息")
    print("4. 收集保诚香港产品信息")
    print("5. 全部收集（需要较长时间）")
    print("0. 退出")
    
    choice = input("\n请选择 (0-5): ").strip()
    
    all_products = []
    
    if choice == '1':
        all_products.extend(crawler.crawl_pingan())
    elif choice == '2':
        all_products.extend(crawler.crawl_chinalife())
    elif choice == '3':
        all_products.extend(crawler.crawl_axa_hk())
    elif choice == '4':
        all_products.extend(crawler.crawl_prudential_hk())
    elif choice == '5':
        all_products.extend(crawler.crawl_pingan())
        all_products.extend(crawler.crawl_chinalife())
        all_products.extend(crawler.crawl_axa_hk())
        all_products.extend(crawler.crawl_prudential_hk())
    elif choice == '0':
        print("退出程序")
        return
    else:
        print("无效选择")
        return
    
    # 导出结果
    if all_products:
        crawler.export_to_excel(all_products)
    
    print("\n收集完成！请查看 insurance_data 目录")


if __name__ == '__main__':
    main()
