#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
保险产品说明书下载工具
半自动化方案，安全合规

使用方式：
1. 手动访问产品页面，复制PDF链接
2. 使用本工具批量下载
3. 自动组织和命名文件
"""

import requests
import os
import time
from urllib.parse import urlparse, unquote
from datetime import datetime
import json

class PDFDownloader:
    """产品说明书PDF下载器"""
    
    def __init__(self, output_dir='insurance_pdfs'):
        self.output_dir = output_dir
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/pdf,*/*',
        })
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        for company in ['AXA', 'Prudential', '平安', '人寿', '其他']:
            os.makedirs(os.path.join(output_dir, company), exist_ok=True)
        
        # 下载历史记录
        self.history_file = os.path.join(output_dir, 'download_history.json')
        self.history = self.load_history()
    
    def load_history(self):
        """加载下载历史"""
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_history(self):
        """保存下载历史"""
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
    
    def download_pdf(self, url, company, product_name, delay=2):
        """
        下载单个PDF文件
        
        Args:
            url: PDF文件的URL
            company: 保险公司名称（AXA/Prudential/平安/人寿）
            product_name: 产品名称
            delay: 下载间隔（秒）
        """
        try:
            # 检查是否已下载
            if url in self.history:
                print(f"⏭️  已下载过: {product_name}")
                return self.history[url]
            
            print(f"📥 正在下载: {product_name}")
            print(f"   URL: {url[:80]}...")
            
            # 礼貌性延迟
            time.sleep(delay)
            
            # 下载文件
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d')
            safe_name = self.sanitize_filename(product_name)
            filename = f"{safe_name}_{timestamp}.pdf"
            filepath = os.path.join(self.output_dir, company, filename)
            
            # 保存文件
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            file_size = len(response.content) / 1024  # KB
            print(f"✅ 下载成功: {filepath}")
            print(f"   文件大小: {file_size:.1f} KB\n")
            
            # 记录历史
            self.history[url] = {
                'filepath': filepath,
                'company': company,
                'product_name': product_name,
                'download_date': timestamp,
                'file_size_kb': file_size
            }
            self.save_history()
            
            return filepath
            
        except requests.RequestException as e:
            print(f"❌ 下载失败: {product_name}")
            print(f"   错误: {e}\n")
            return None
        except Exception as e:
            print(f"❌ 保存失败: {product_name}")
            print(f"   错误: {e}\n")
            return None
    
    def sanitize_filename(self, name):
        """清理文件名，移除非法字符"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name.strip()
    
    def download_batch(self, pdf_list, delay=3):
        """
        批量下载PDF
        
        Args:
            pdf_list: PDF信息列表，格式：[
                {'url': 'xxx', 'company': 'AXA', 'product_name': 'xxx'},
                ...
            ]
            delay: 下载间隔（秒）
        """
        print("="*80)
        print(f"开始批量下载，共 {len(pdf_list)} 个文件")
        print(f"下载间隔: {delay} 秒")
        print("="*80 + "\n")
        
        success_count = 0
        failed_count = 0
        
        for i, item in enumerate(pdf_list, 1):
            print(f"[{i}/{len(pdf_list)}]")
            result = self.download_pdf(
                url=item['url'],
                company=item['company'],
                product_name=item['product_name'],
                delay=delay
            )
            
            if result:
                success_count += 1
            else:
                failed_count += 1
        
        print("="*80)
        print(f"下载完成！")
        print(f"  成功: {success_count}")
        print(f"  失败: {failed_count}")
        print(f"  跳过: {len(pdf_list) - success_count - failed_count}")
        print("="*80)
    
    def show_history(self):
        """显示下载历史"""
        if not self.history:
            print("暂无下载历史")
            return
        
        print("\n" + "="*80)
        print("下载历史")
        print("="*80)
        
        for url, info in self.history.items():
            print(f"\n产品: {info['product_name']}")
            print(f"公司: {info['company']}")
            print(f"文件: {info['filepath']}")
            print(f"日期: {info['download_date']}")
            print(f"大小: {info['file_size_kb']:.1f} KB")


def create_sample_list():
    """创建示例下载列表模板"""
    sample = [
        {
            "url": "https://www.axa.com.hk/zh/wealth-ahead-ii-savings-insurance/product-brochure.pdf",
            "company": "AXA",
            "product_name": "盛利II储蓄保险",
            "说明": "将此模板复制，填写实际的PDF链接"
        },
        {
            "url": "https://www.prudential.com.hk/sc/products/savings/product-brochure.pdf",
            "company": "Prudential",
            "product_name": "保诚信守明天",
            "说明": "从产品页面复制PDF下载链接"
        }
    ]
    
    with open('download_list.json', 'w', encoding='utf-8') as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    
    print("✅ 已创建示例文件: download_list.json")
    print("\n使用说明：")
    print("1. 打开 download_list.json")
    print("2. 按照格式添加您要下载的PDF链接")
    print("3. 运行下载命令")


def main():
    """主函数"""
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║        保险产品说明书下载工具 v1.0                            ║
    ║        半自动化、安全、合规                                    ║
    ╚════════════════════════════════════════════════════════════════╝
    
    重要提示：
    1. 本工具用于下载您手动找到的PDF链接
    2. 请从保险公司官网合法获取链接
    3. 仅供个人学习研究使用
    4. 设置了合理的下载间隔，避免给服务器造成压力
    
    ======================================================================
    
    使用流程：
    
    步骤1: 手动访问保险公司官网
           - 浏览产品页面
           - 找到"产品说明书"或"产品小册子"
           - 右键点击"另存为"或"复制链接"
    
    步骤2: 将PDF链接整理到 download_list.json
           - 运行功能1创建模板
           - 填写实际的PDF链接
    
    步骤3: 运行批量下载
           - 选择功能2
           - 工具会自动下载并组织文件
    
    ======================================================================
    """)
    
    downloader = PDFDownloader()
    
    while True:
        print("\n可用功能：")
        print("  1. 创建下载列表模板")
        print("  2. 从列表文件批量下载")
        print("  3. 下载单个PDF（交互式）")
        print("  4. 查看下载历史")
        print("  0. 退出")
        
        choice = input("\n请选择功能 (0-4): ").strip()
        
        if choice == '1':
            create_sample_list()
            print("\n📝 下一步：")
            print("   1. 打开 download_list.json")
            print("   2. 访问保险公司官网，复制PDF链接")
            print("   3. 按照格式填写到文件中")
            print("   4. 保存后运行功能2进行下载")
        
        elif choice == '2':
            if not os.path.exists('download_list.json'):
                print("❌ 未找到 download_list.json")
                print("   请先运行功能1创建模板")
                continue
            
            try:
                with open('download_list.json', 'r', encoding='utf-8') as f:
                    pdf_list = json.load(f)
                
                # 移除示例中的"说明"字段
                pdf_list = [
                    {k: v for k, v in item.items() if k != '说明'}
                    for item in pdf_list
                ]
                
                print(f"\n找到 {len(pdf_list)} 个待下载项")
                confirm = input("确认开始下载？(y/n): ").strip().lower()
                
                if confirm == 'y':
                    delay = input("下载间隔（秒，建议3-5）[默认3]: ").strip()
                    delay = int(delay) if delay else 3
                    downloader.download_batch(pdf_list, delay=delay)
                else:
                    print("已取消")
                    
            except json.JSONDecodeError:
                print("❌ JSON格式错误，请检查文件格式")
            except Exception as e:
                print(f"❌ 错误: {e}")
        
        elif choice == '3':
            print("\n请输入PDF信息：")
            url = input("PDF链接: ").strip()
            company = input("公司名称(AXA/Prudential/平安/人寿/其他): ").strip()
            product_name = input("产品名称: ").strip()
            
            if url and company and product_name:
                downloader.download_pdf(url, company, product_name)
            else:
                print("❌ 信息不完整")
        
        elif choice == '4':
            downloader.show_history()
        
        elif choice == '0':
            print("\n感谢使用！")
            break
        
        else:
            print("无效选择")


if __name__ == '__main__':
    main()
