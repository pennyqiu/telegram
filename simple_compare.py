#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
保险产品简单对比工具（无需额外依赖）
"""

import json
import os
from glob import glob
from datetime import datetime

class SimpleComparator:
    """简单对比器"""
    
    def __init__(self):
        self.products = []
    
    def load_products(self, pattern='*.json'):
        """加载所有产品JSON文件"""
        files = glob(pattern)
        
        # 排除模板和示例文件
        files = [f for f in files if not f.startswith('insurance_template') 
                 and not f.startswith('示例_')]
        
        for filepath in files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    product = json.load(f)
                    product['_source_file'] = filepath
                    self.products.append(product)
                print(f"✅ 已加载: {filepath}")
            except Exception as e:
                print(f"❌ 加载失败 {filepath}: {e}")
        
        print(f"\n共加载 {len(self.products)} 个产品")
        return len(self.products)
    
    def print_summary(self):
        """打印产品摘要"""
        if not self.products:
            print("未加载任何产品")
            return
        
        print("\n" + "="*80)
        print("产品摘要")
        print("="*80)
        
        for i, product in enumerate(self.products, 1):
            basic = product.get('基本信息', {})
            cost = product.get('费用结构', {})
            rating = product.get('个人评估', {})
            
            print(f"\n【{i}】{basic.get('产品名称', '未命名')}")
            print(f"    公司：{basic.get('保险公司', 'N/A')}")
            print(f"    类型：{basic.get('产品类型', 'N/A')}")
            print(f"    年缴：{cost.get('年缴保费', 0):,.0f} {basic.get('币种', '')}")
            print(f"    评分：{rating.get('综合评分_10分制', 0)}/10")
            print(f"    考虑：{rating.get('是否考虑购买', '待定')}")
    
    def compare_savings_products(self):
        """对比储蓄类产品"""
        savings = [p for p in self.products 
                   if '储蓄' in p.get('基本信息', {}).get('产品类型', '')]
        
        if not savings:
            print("没有储蓄类产品")
            return
        
        print("\n" + "="*100)
        print("储蓄类产品对比")
        print("="*100)
        
        # 表头
        print(f"\n{'产品名称':<30} {'年缴':<12} {'总缴费':<12} {'预期收益率':<10} {'回本年期':<10} {'评分':<8}")
        print("-" * 100)
        
        for product in savings:
            basic = product.get('基本信息', {})
            cost = product.get('费用结构', {})
            returns = product.get('收益分析_储蓄类', {})
            rating = product.get('个人评估', {})
            
            name = basic.get('产品名称', '')[:28]
            annual = cost.get('年缴保费', 0)
            total = cost.get('总缴费金额', 0)
            irr = returns.get('预期总收益率_年化', 0)
            breakeven = returns.get('回本年期', 0)
            score = rating.get('综合评分_10分制', 0)
            
            print(f"{name:<30} {annual:>10,.0f}  {total:>10,.0f}  {irr:>8.1f}%  {breakeven:>8}年  {score:>6.1f}/10")
        
        # 详细收益对比
        print("\n" + "="*100)
        print("现金价值对比（关键年份）")
        print("="*100)
        
        years = ['第5年', '第10年', '第20年', '第30年']
        print(f"\n{'产品名称':<30} {' '.join([f'{y:<15}' for y in years])}")
        print("-" * 100)
        
        for product in savings:
            basic = product.get('基本信息', {})
            returns = product.get('收益分析_储蓄类', {})
            cash_value = returns.get('现金价值', {})
            
            name = basic.get('产品名称', '')[:28]
            values = []
            for year in years:
                val = cash_value.get(year, 0)
                values.append(f"{val:>13,.0f}")
            
            print(f"{name:<30} {' '.join(values)}")
    
    def compare_ci_products(self):
        """对比重疾险产品"""
        ci = [p for p in self.products 
              if '重疾' in p.get('基本信息', {}).get('产品类型', '')]
        
        if not ci:
            print("没有重疾险产品")
            return
        
        print("\n" + "="*100)
        print("重疾险产品对比")
        print("="*100)
        
        print(f"\n{'产品名称':<30} {'年缴':<12} {'基本保额':<12} {'理赔时效':<10} {'评分':<8}")
        print("-" * 100)
        
        for product in ci:
            basic = product.get('基本信息', {})
            cost = product.get('费用结构', {})
            coverage = product.get('保障内容', {})
            claims = product.get('理赔服务_医疗重疾类', {})
            rating = product.get('个人评估', {})
            
            name = basic.get('产品名称', '')[:28]
            annual = cost.get('年缴保费', 0)
            sum_insured = coverage.get('基本保额', 0)
            claim_days = claims.get('理赔时效_工作日', 0)
            score = rating.get('综合评分_10分制', 0)
            
            print(f"{name:<30} {annual:>10,.0f}  {sum_insured:>10,.0f}  {claim_days:>8}天  {score:>6.1f}/10")
    
    def show_product_detail(self, index):
        """显示产品详情"""
        if index < 0 or index >= len(self.products):
            print("无效的产品索引")
            return
        
        product = self.products[index]
        basic = product.get('基本信息', {})
        
        print("\n" + "="*80)
        print(f"产品详情：{basic.get('产品名称', '未命名')}")
        print("="*80)
        
        # 基本信息
        print("\n【基本信息】")
        for key, value in basic.items():
            print(f"  {key}: {value}")
        
        # 费用结构
        cost = product.get('费用结构', {})
        print("\n【费用结构】")
        for key, value in cost.items():
            print(f"  {key}: {value}")
        
        # 优缺点
        pros_cons = product.get('优缺点分析', {})
        print("\n【优势】")
        for advantage in pros_cons.get('主要优势', []):
            print(f"  ✓ {advantage}")
        
        print("\n【劣势】")
        for disadvantage in pros_cons.get('主要劣势', []):
            print(f"  ✗ {disadvantage}")
        
        # 个人评估
        rating = product.get('个人评估', {})
        print("\n【个人评估】")
        print(f"  综合评分: {rating.get('综合评分_10分制', 0)}/10")
        print(f"  性价比: {rating.get('性价比评分_10分制', 0)}/10")
        print(f"  适合度: {rating.get('适合度评分_10分制', 0)}/10")
        print(f"  是否考虑: {rating.get('是否考虑购买', '待定')}")
        print(f"\n  决策要点:")
        for point in rating.get('决策要点', []):
            print(f"    • {point}")
        if rating.get('备注'):
            print(f"\n  备注: {rating.get('备注')}")
    
    def export_comparison_report(self):
        """导出对比报告（文本格式）"""
        if not self.products:
            print("没有产品可导出")
            return
        
        filename = f'对比报告_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("保险产品对比报告\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"产品数量: {len(self.products)}\n")
            f.write("="*80 + "\n\n")
            
            for i, product in enumerate(self.products, 1):
                basic = product.get('基本信息', {})
                f.write(f"\n{'='*80}\n")
                f.write(f"产品 {i}: {basic.get('产品名称', '未命名')}\n")
                f.write(f"{'='*80}\n\n")
                
                # 写入所有信息
                for section, data in product.items():
                    if section != '_source_file':
                        f.write(f"【{section}】\n")
                        if isinstance(data, dict):
                            for key, value in data.items():
                                f.write(f"  {key}: {value}\n")
                        else:
                            f.write(f"  {data}\n")
                        f.write("\n")
        
        print(f"✅ 已导出对比报告: {filename}")
    
    def family_analysis(self):
        """简单的家庭配置分析"""
        print("\n" + "="*80)
        print("家庭保险配置建议（基于《港险投保30问》）")
        print("="*80)
        
        print("\n请输入您的家庭信息：")
        try:
            age = int(input("主要投保人年龄: "))
            income = float(input("家庭年收入（元）: "))
            has_kids = input("是否有子女（是/否）: ").strip() == '是'
            
            print("\n" + "="*80)
            print("配置优先级建议")
            print("="*80)
            
            budget = income * 0.125
            print(f"\n建议保费预算：{budget:,.0f} 元/年（年收入的12.5%）")
            
            print("\n【优先级1：医疗保险】")
            if income < 500000:
                print("  推荐：VHIS自愿医保")
                print("  预算：每人约 5,000-10,000 港币/年")
            else:
                print("  推荐：高端医疗保险")
                print("  预算：每人约 20,000-50,000 港币/年")
            
            print("\n【优先级2：重疾险】")
            if age < 40:
                print("  推荐：多次赔付重疾险")
                print(f"  建议保额：{income * 5:,.0f} - {income * 10:,.0f} 元（年收入的5-10倍）")
            else:
                print("  推荐：单次赔付重疾险或重疾+医疗组合")
                print(f"  建议保额：{income * 3:,.0f} - {income * 5:,.0f} 元（年收入的3-5倍）")
            
            print("\n【优先级3：储蓄分红险】")
            if income > 300000:
                print("  推荐：美元储蓄分红险")
                print("  建议：在完成医疗和重疾配置后，用余额的50-70%配置")
            else:
                print("  建议：先完成保障型产品配置")
            
            if has_kids:
                print("\n【可选：子女教育金】")
                print("  推荐：储蓄分红险+教育金专项")
                print("  提示：越早开始越好，利用复利优势")
            
            print("\n" + "="*80)
            
            # 在已加载的产品中找匹配的
            if self.products:
                print("\n您已收集的产品中，推荐关注：")
                for product in self.products:
                    basic = product.get('基本信息', {})
                    适用 = product.get('适用场景', {})
                    if income >= 300000 and '中产' in str(适用.get('推荐人群', [])):
                        print(f"  ✓ {basic.get('产品名称', '')}")
            
        except ValueError:
            print("输入格式错误")


def main():
    """主函数"""
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║           保险产品对比工具 v1.0（简化版）                      ║
    ║           无需额外依赖，直接运行                               ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    comparator = SimpleComparator()
    
    # 自动加载当前目录的所有JSON文件
    count = comparator.load_products()
    
    if count == 0:
        print("\n💡 提示：当前目录没有产品数据文件")
        print("   请先运行 python3 generate_template.py 生成模板")
        print("   然后填写产品信息后再运行本工具")
        return
    
    while True:
        print("\n" + "="*80)
        print("可用功能：")
        print("  1. 产品摘要")
        print("  2. 储蓄类产品对比")
        print("  3. 重疾险产品对比")
        print("  4. 查看产品详情")
        print("  5. 家庭保险配置分析")
        print("  6. 导出对比报告")
        print("  0. 退出")
        print("="*80)
        
        choice = input("\n请选择功能 (0-6): ").strip()
        
        if choice == '1':
            comparator.print_summary()
        
        elif choice == '2':
            comparator.compare_savings_products()
        
        elif choice == '3':
            comparator.compare_ci_products()
        
        elif choice == '4':
            comparator.print_summary()
            try:
                index = int(input("\n请输入产品编号: ")) - 1
                comparator.show_product_detail(index)
            except ValueError:
                print("无效输入")
        
        elif choice == '5':
            comparator.family_analysis()
        
        elif choice == '6':
            comparator.export_comparison_report()
        
        elif choice == '0':
            print("\n感谢使用！祝您找到最适合的保险配置方案 🎯")
            break
        
        else:
            print("无效选择")


if __name__ == '__main__':
    main()
