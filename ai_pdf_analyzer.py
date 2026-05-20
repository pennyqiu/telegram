#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI PDF分析工具
使用AI批量分析保险产品PDF，自动提取关键信息

支持：
1. 本地大模型（Ollama）
2. OpenAI API
3. Claude API
4. 批量分析多个PDF
5. 自动填充产品模板
"""

import json
import os
from datetime import datetime
import PyPDF2

class PDFAnalyzer:
    """PDF分析器"""
    
    def __init__(self, api_type='ollama'):
        """
        初始化分析器
        
        Args:
            api_type: 'ollama' / 'openai' / 'claude'
        """
        self.api_type = api_type
        self.extracted_data = []
    
    def extract_text_from_pdf(self, pdf_path):
        """从PDF提取文本"""
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                
                # 提取前10页（通常包含关键信息）
                max_pages = min(10, len(reader.pages))
                
                for i in range(max_pages):
                    page = reader.pages[i]
                    text += page.extract_text()
                
                return text
        except Exception as e:
            print(f"❌ PDF读取失败 {pdf_path}: {e}")
            return None
    
    def analyze_with_prompt(self, pdf_text, product_name):
        """使用AI分析PDF内容"""
        
        prompt = f"""
请分析以下保险产品说明书，提取关键信息。产品名称：{product_name}

PDF内容：
{pdf_text[:4000]}  # 限制长度避免token过多

请按以下JSON格式输出：
{{
  "产品名称": "",
  "保险公司": "",
  "产品类型": "储蓄分红/重疾险/医疗险/年金险",
  "币种": "美元/港币/人民币",
  "投保年龄": "",
  "保险期限": "",
  "年缴保费_参考": 0,
  "缴费年期": 0,
  "基本保额_参考": 0,
  "保证收益率": 0,
  "预期总收益率": 0,
  "回本年期": 0,
  "主要优势": [],
  "主要劣势": [],
  "适合人群": []
}}

只输出JSON，不要其他说明文字。
"""
        
        # 这里根据不同的API调用相应的服务
        if self.api_type == 'ollama':
            return self._call_ollama(prompt)
        elif self.api_type == 'openai':
            return self._call_openai(prompt)
        elif self.api_type == 'claude':
            return self._call_claude(prompt)
        else:
            return self._mock_analysis(product_name)
    
    def _mock_analysis(self, product_name):
        """模拟分析结果（用于测试）"""
        return {
            "产品名称": product_name,
            "保险公司": "AXA",
            "产品类型": "储蓄分红",
            "币种": "美元",
            "投保年龄": "0-70周岁",
            "保险期限": "终身",
            "年缴保费_参考": 50000,
            "缴费年期": 5,
            "基本保额_参考": 250000,
            "保证收益率": 1.2,
            "预期总收益率": 5.5,
            "回本年期": 7,
            "主要优势": [
                "AI提取：需要实际运行AI分析",
                "这是模拟数据"
            ],
            "主要劣势": [
                "AI提取：需要实际运行AI分析"
            ],
            "适合人群": [
                "AI提取：需要实际运行AI分析"
            ],
            "_note": "这是模拟数据，需要配置AI API才能获得真实分析"
        }
    
    def _call_ollama(self, prompt):
        """调用本地Ollama"""
        try:
            import requests
            
            response = requests.post(
                'http://localhost:11434/api/generate',
                json={
                    'model': 'llama3',  # 或其他模型
                    'prompt': prompt,
                    'stream': False
                }
            )
            
            result = response.json()
            # 解析JSON
            return json.loads(result['response'])
        except Exception as e:
            print(f"❌ Ollama调用失败: {e}")
            print("💡 提示：请确保Ollama已启动：ollama serve")
            return None
    
    def _call_openai(self, prompt):
        """调用OpenAI API"""
        try:
            import openai
            
            # 需要设置 OPENAI_API_KEY 环境变量
            openai.api_key = os.getenv('OPENAI_API_KEY')
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "你是保险产品分析专家"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            result = response.choices[0].message.content
            return json.loads(result)
        except Exception as e:
            print(f"❌ OpenAI调用失败: {e}")
            return None
    
    def _call_claude(self, prompt):
        """调用Claude API"""
        try:
            import anthropic
            
            client = anthropic.Anthropic(
                api_key=os.getenv('ANTHROPIC_API_KEY')
            )
            
            message = client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=2048,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            result = message.content[0].text
            return json.loads(result)
        except Exception as e:
            print(f"❌ Claude调用失败: {e}")
            return None
    
    def analyze_pdf(self, pdf_path, product_name):
        """分析单个PDF"""
        print(f"\n📄 正在分析: {product_name}")
        print(f"   文件: {pdf_path}")
        
        # 提取文本
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            return None
        
        print(f"   提取了 {len(text)} 个字符")
        
        # AI分析
        print(f"   正在使用 {self.api_type} 分析...")
        result = self.analyze_with_prompt(text, product_name)
        
        if result:
            print(f"   ✅ 分析完成")
            result['_source_pdf'] = pdf_path
            result['_analysis_date'] = datetime.now().strftime('%Y-%m-%d')
            return result
        else:
            print(f"   ❌ 分析失败")
            return None
    
    def batch_analyze(self, pdf_dir='insurance_pdfs', company='AXA'):
        """批量分析PDF"""
        print("="*80)
        print(f"批量分析 {company} 产品")
        print("="*80)
        
        # 查找PDF文件
        pdf_files = []
        company_dir = os.path.join(pdf_dir, company)
        
        if os.path.exists(company_dir):
            for filename in os.listdir(company_dir):
                if filename.endswith('.pdf'):
                    pdf_path = os.path.join(company_dir, filename)
                    # 从文件名提取产品名称
                    product_name = filename.replace('.pdf', '').rsplit('_', 1)[0]
                    pdf_files.append((pdf_path, product_name))
        
        if not pdf_files:
            print(f"❌ 未找到PDF文件在 {company_dir}")
            return
        
        print(f"找到 {len(pdf_files)} 个PDF文件\n")
        
        # 逐个分析
        results = []
        for i, (pdf_path, product_name) in enumerate(pdf_files, 1):
            print(f"\n[{i}/{len(pdf_files)}]")
            result = self.analyze_pdf(pdf_path, product_name)
            
            if result:
                results.append(result)
        
        self.extracted_data = results
        
        print("\n" + "="*80)
        print(f"分析完成！成功: {len(results)}/{len(pdf_files)}")
        print("="*80)
        
        return results
    
    def export_to_templates(self, output_dir='ai_analyzed'):
        """导出为产品模板格式"""
        os.makedirs(output_dir, exist_ok=True)
        
        for data in self.extracted_data:
            # 加载标准模板
            template_path = 'insurance_template.json'
            if os.path.exists(template_path):
                with open(template_path, 'r', encoding='utf-8') as f:
                    template = json.load(f)
            else:
                template = {}
            
            # 填充AI提取的数据
            if '基本信息' in template:
                template['基本信息']['产品名称'] = data.get('产品名称', '')
                template['基本信息']['保险公司'] = data.get('保险公司', '')
                template['基本信息']['产品类型'] = data.get('产品类型', '')
                template['基本信息']['币种'] = data.get('币种', '')
                template['基本信息']['投保年龄'] = data.get('投保年龄', '')
                template['基本信息']['保险期限'] = data.get('保险期限', '')
            
            if '费用结构' in template:
                template['费用结构']['年缴保费'] = data.get('年缴保费_参考', 0)
                template['费用结构']['缴费年期'] = data.get('缴费年期', 0)
            
            if '收益分析_储蓄类' in template:
                template['收益分析_储蓄类']['保证收益率_年化'] = data.get('保证收益率', 0)
                template['收益分析_储蓄类']['预期总收益率_年化'] = data.get('预期总收益率', 0)
                template['收益分析_储蓄类']['回本年期'] = data.get('回本年期', 0)
            
            if '优缺点分析' in template:
                template['优缺点分析']['主要优势'] = data.get('主要优势', [])
                template['优缺点分析']['主要劣势'] = data.get('主要劣势', [])
            
            if '适用场景' in template:
                template['适用场景']['推荐人群'] = data.get('适合人群', [])
            
            # 保存
            product_name = data.get('产品名称', 'unknown').replace('/', '_')
            filename = f"{product_name}_AI分析_{datetime.now().strftime('%Y%m%d')}.json"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(template, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 已导出: {filepath}")
        
        print(f"\n所有文件已导出到: {output_dir}/")


def main():
    """主函数"""
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║        AI PDF分析工具 v1.0                                     ║
    ║        自动提取保险产品关键信息                                 ║
    ╚════════════════════════════════════════════════════════════════╝
    
    功能：
    1. 从PDF提取文本
    2. 使用AI分析关键信息
    3. 自动填充产品模板
    4. 批量处理多个产品
    
    支持的AI服务：
    - Ollama (本地免费，推荐)
    - OpenAI GPT-4
    - Claude
    
    ══════════════════════════════════════════════════════════════════
    """)
    
    print("\n选择AI服务：")
    print("1. Ollama (本地免费) - 推荐")
    print("2. OpenAI GPT-4")
    print("3. Claude")
    print("4. 模拟模式（测试用）")
    
    choice = input("\n请选择 (1-4): ").strip()
    
    api_map = {
        '1': 'ollama',
        '2': 'openai',
        '3': 'claude',
        '4': 'mock'
    }
    
    api_type = api_map.get(choice, 'mock')
    
    analyzer = PDFAnalyzer(api_type=api_type)
    
    print("\n模式选择：")
    print("1. 批量分析AXA产品")
    print("2. 分析单个PDF")
    print("3. 批量分析其他公司")
    
    mode = input("\n请选择 (1-3): ").strip()
    
    if mode == '1':
        results = analyzer.batch_analyze(company='AXA')
        if results:
            analyzer.export_to_templates()
    
    elif mode == '2':
        pdf_path = input("PDF文件路径: ").strip()
        product_name = input("产品名称: ").strip()
        
        result = analyzer.analyze_pdf(pdf_path, product_name)
        if result:
            print("\n分析结果：")
            print(json.dumps(result, ensure_ascii=False, indent=2))
    
    elif mode == '3':
        company = input("公司名称（Prudential/平安/人寿）: ").strip()
        results = analyzer.batch_analyze(company=company)
        if results:
            analyzer.export_to_templates()
    
    print("""
    
    ══════════════════════════════════════════════════════════════════
    💡 提示：
    1. AI提取的数据仅供参考，请人工复核
    2. 重要信息务必对照原PDF确认
    3. 生成的模板可以继续手工完善
    ══════════════════════════════════════════════════════════════════
    """)


if __name__ == '__main__':
    main()
