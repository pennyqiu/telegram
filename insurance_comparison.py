#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
保险产品对比分析工具
用于系统化地比较和评估不同保险产品
"""

import pandas as pd
import json
from datetime import datetime
from typing import Dict, List
import os

class InsuranceComparator:
    """保险产品对比分析器"""
    
    def __init__(self):
        self.products = []
        self.comparison_framework = self.build_comparison_framework()
    
    def build_comparison_framework(self) -> Dict:
        """构建对比框架（基于港险投保30问的知识）"""
        return {
            '基本信息': {
                '产品名称': '',
                '保险公司': '',
                '产品类型': '',  # 储蓄分红/重疾/医疗/年金/万用寿险
                '币种': '',  # 美元/港币/人民币
                '投保年龄': '',
                '保险期限': '',
            },
            '费用结构': {
                '年缴保费': 0,
                '缴费年期': 0,
                '总缴费金额': 0,
                '首期保费': 0,
            },
            '保障内容': {
                '基本保额': 0,
                '保障范围': [],
                '特色保障': [],
                '免责条款': [],
            },
            '收益分析（储蓄类）': {
                '保证收益率': 0,
                '预期总收益率': 0,
                '非保证收益率': 0,
                '分红实现率_历史': '',  # 过去5-10年数据
                '第5年现金价值': 0,
                '第10年现金价值': 0,
                '第20年现金价值': 0,
                '回本年期': 0,
            },
            '流动性': {
                '冷静期': 21,  # 天
                '保单贷款比例': 0,  # %
                '减额缴清': '',  # 是/否
                '保费假期': '',  # 是/否
                '第1年退保损失率': 0,
                '第3年退保损失率': 0,
                '第5年退保损失率': 0,
            },
            '理赔服务': {
                '理赔网络': [],  # 支持的医院范围
                '直付服务': '',  # 是/否
                '理赔时效': '',  # 工作日
                '免赔额': 0,
                '赔付比例': 0,
            },
            '税务相关': {
                'CRS申报': '',  # 是/否
                '传承功能': '',  # 受益人指定等
                '跨境税务影响': '',
            },
            '公司评级': {
                '成立年份': 0,
                '资本规模': '',
                'HKIA评级': '',
                '历史分红实现率': '',
            },
            '适用场景': {
                '推荐人群': [],
                '配置优先级': '',  # 高/中/低
                '与其他产品搭配': [],
            },
            '优缺点分析': {
                '主要优势': [],
                '主要劣势': [],
                '对比同类竞品': '',
            },
            '个人评分': {
                '综合评分': 0,  # 1-10分
                '性价比': 0,
                '适合度': 0,
                '备注': '',
            }
        }
    
    def add_product(self, product_info: Dict):
        """添加产品信息"""
        self.products.append(product_info)
    
    def load_from_json(self, filepath: str):
        """从JSON文件加载产品信息"""
        with open(filepath, 'r', encoding='utf-8') as f:
            product = json.load(f)
            self.add_product(product)
    
    def save_template(self, filepath='insurance_template.json'):
        """保存产品信息模板"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.comparison_framework, f, ensure_ascii=False, indent=2)
        print(f"已保存模板文件: {filepath}")
        print("您可以复制此模板，填写每个产品的信息")
    
    def compare_products(self, product_type='all'):
        """对比产品"""
        if not self.products:
            print("还没有添加任何产品信息")
            return None
        
        # 根据产品类型筛选
        if product_type != 'all':
            filtered_products = [p for p in self.products 
                               if p.get('基本信息', {}).get('产品类型') == product_type]
        else:
            filtered_products = self.products
        
        if not filtered_products:
            print(f"没有找到类型为 {product_type} 的产品")
            return None
        
        # 创建对比表
        comparison_data = []
        for product in filtered_products:
            row = {
                '产品名称': product.get('基本信息', {}).get('产品名称', ''),
                '保险公司': product.get('基本信息', {}).get('保险公司', ''),
                '年缴保费': product.get('费用结构', {}).get('年缴保费', 0),
                '总缴费': product.get('费用结构', {}).get('总缴费金额', 0),
                '基本保额': product.get('保障内容', {}).get('基本保额', 0),
                '预期收益率': product.get('收益分析（储蓄类）', {}).get('预期总收益率', 0),
                '回本年期': product.get('收益分析（储蓄类）', {}).get('回本年期', 0),
                '综合评分': product.get('个人评分', {}).get('综合评分', 0),
            }
            comparison_data.append(row)
        
        df = pd.DataFrame(comparison_data)
        return df
    
    def export_comparison(self, output_dir='insurance_data'):
        """导出对比报告"""
        os.makedirs(output_dir, exist_ok=True)
        
        # 导出Excel
        excel_file = os.path.join(output_dir, f'保险产品对比_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
        
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            # 总览表
            df_all = self.compare_products('all')
            if df_all is not None:
                df_all.to_excel(writer, sheet_name='全部产品', index=False)
            
            # 按类型分类
            for product_type in ['储蓄分红', '重疾险', '医疗险', '年金险', '万用寿险']:
                df = self.compare_products(product_type)
                if df is not None and not df.empty:
                    df.to_excel(writer, sheet_name=product_type, index=False)
        
        print(f"已导出对比报告: {excel_file}")
        
        # 导出详细JSON
        json_file = os.path.join(output_dir, f'保险产品详细_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(self.products, f, ensure_ascii=False, indent=2)
        print(f"已导出详细信息: {json_file}")
    
    def analyze_for_family(self, family_profile: Dict):
        """基于家庭情况进行产品推荐分析"""
        print("\n" + "="*60)
        print("家庭保险配置分析")
        print("="*60)
        
        # 提取家庭信息
        age = family_profile.get('年龄', 0)
        annual_income = family_profile.get('年收入', 0)
        family_size = family_profile.get('家庭人数', 1)
        has_kids = family_profile.get('有子女', False)
        risk_tolerance = family_profile.get('风险承受能力', '中')
        
        recommendations = []
        
        # 配置优先级逻辑（基于港险投保30问）
        print("\n根据您的家庭情况，建议配置优先级：")
        print("\n1. 医疗保险（高优先级）")
        if annual_income < 500000:
            print("   推荐：VHIS自愿医保")
            recommendations.append('VHIS自愿医保')
        else:
            print("   推荐：高端医疗保险")
            recommendations.append('高端医疗保险')
        
        print("\n2. 重疾险（高优先级）")
        if age < 40:
            print("   推荐：多次赔付重疾险，保额建议年收入的5-10倍")
            recommendations.append('多次赔付重疾险')
        else:
            print("   推荐：单次赔付重疾险或重疾+医疗组合")
            recommendations.append('单次赔付重疾险')
        
        print("\n3. 储蓄分红险（中优先级）")
        if annual_income > 300000 and risk_tolerance in ['中', '高']:
            print("   推荐：美元储蓄分红险，作为长期资产配置")
            recommendations.append('储蓄分红险')
        else:
            print("   建议：先配置保障型产品，有余力再考虑")
        
        print("\n4. 年金险（低优先级）")
        if age > 35 and annual_income > 500000:
            print("   推荐：延期年金，提前规划退休")
            recommendations.append('延期年金')
        else:
            print("   建议：40岁后再考虑配置")
        
        if has_kids:
            print("\n5. 子女教育金（可选）")
            print("   推荐：储蓄分红险+教育金专项")
            recommendations.append('教育金储蓄')
        
        print("\n" + "="*60)
        print("建议年保费预算：年收入的10-15%")
        recommended_budget = annual_income * 0.125
        print(f"根据您的年收入 {annual_income:,.0f} 元")
        print(f"建议保费预算：{recommended_budget:,.0f} 元/年")
        print("="*60)
        
        return recommendations


def main():
    """主函数"""
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║           保险产品对比分析工具 v1.0                            ║
    ║           基于《港险投保30问》知识框架                         ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    comparator = InsuranceComparator()
    
    print("\n可用功能:")
    print("1. 生成产品信息模板")
    print("2. 加载已有产品数据")
    print("3. 对比产品")
    print("4. 家庭保险配置分析")
    print("5. 导出对比报告")
    print("0. 退出")
    
    while True:
        choice = input("\n请选择功能 (0-5): ").strip()
        
        if choice == '1':
            comparator.save_template()
            print("\n提示：请复制 insurance_template.json 为具体产品名称")
            print("填写完每个产品后，使用功能2加载")
            
        elif choice == '2':
            filepath = input("请输入产品JSON文件路径: ").strip()
            if os.path.exists(filepath):
                comparator.load_from_json(filepath)
                print(f"已加载产品信息")
            else:
                print("文件不存在")
        
        elif choice == '3':
            product_type = input("请输入产品类型(all/储蓄分红/重疾险/医疗险/年金险/万用寿险): ").strip()
            df = comparator.compare_products(product_type if product_type else 'all')
            if df is not None:
                print("\n" + "="*80)
                print(df.to_string())
                print("="*80)
        
        elif choice == '4':
            print("\n请输入您的家庭信息：")
            family_profile = {
                '年龄': int(input("主要投保人年龄: ")),
                '年收入': float(input("家庭年收入(元): ")),
                '家庭人数': int(input("家庭人数: ")),
                '有子女': input("是否有子女(是/否): ").strip() == '是',
                '风险承受能力': input("风险承受能力(低/中/高): ").strip(),
            }
            comparator.analyze_for_family(family_profile)
        
        elif choice == '5':
            comparator.export_comparison()
        
        elif choice == '0':
            print("退出程序")
            break
        
        else:
            print("无效选择")


if __name__ == '__main__':
    main()
