"""Day 11 任务2+3测试：验证 embedding API + 相似度实验"""
import sys
from pathlib import Path

# 关键：添加项目根目录到 sys.path，确保能导入 code.shared 等模块
project_root = Path(__file__).resolve().parents[2]  # 上溯3级到仓库根目录
sys.path.insert(0, str(project_root))

from code.week03.mini_rag.embeddings import get_embed_fn, load_embed_settings
from code.week03.mini_rag.similarity import cosine, similarity_matrix, top_k

def test_embedding_api():
    # 1. 验证配置加载
    print("=== 1. 加载配置 ===")
    try:
        settings = load_embed_settings()
        print(f"✓ 配置加载成功")
        print(f"  Model: {settings.model}")
        print(f"  Dimensions: {settings.dimensions or '默认'}")
    except Exception as e:
        print(f"✗ 配置加载失败: {e}")
        return False

    # 2. 获取嵌入函数（batch_size=2 测试分批）
    print("\n=== 2. 初始化嵌入函数 ===")
    embed = get_embed_fn(batch_size=2)

    # 3. 准备 5 条测试文本（应分 3 批请求）
    texts = [
        "如何申请退款",
        "退款流程是什么", 
        "怎么开发票",
        "发票抬头可以修改吗",
        "今天天气怎么样",
    ]
    
    print(f"\n=== 3. 嵌入 {len(texts)} 条文本（batch_size=2）===")
    try:
        vectors = embed(texts)
        print(f"✓ 嵌入成功，返回 {len(vectors)} 条向量")
    except Exception as e:
        print(f"✗ 嵌入失败: {e}")
        return False

    # 4. 验证维度
    dim = len(vectors[0])
    print(f"\n=== 4. 维度检查 ===")
    print(f"向量维度: {dim}")

    # 5. 语义验证（核心）
    print(f"\n=== 5. 语义相似度验证 ===")
    test_pairs = [
        (0, 1, "退款 vs 退款流程", "应较高"),
        (2, 3, "发票 vs 发票抬头", "应较高"),
        (0, 4, "退款 vs 天气", "应较低"),
    ]
    
    for i, j, desc, _ in test_pairs:
        score = cosine(vectors[i], vectors[j])
        print(f"  {desc}: {score:.3f}")

    # 断言：相似 > 不相似
    sim_related = cosine(vectors[0], vectors[1])
    sim_unrelated = cosine(vectors[0], vectors[4])
    
    print(f"\n=== 6. 最终验证 ===")
    if sim_related > sim_unrelated:
        print(f"✓ 测试通过：相关({sim_related:.3f}) > 无关({sim_unrelated:.3f})")
        return True
    else:
        print(f"✗ 测试失败")
        return False

def test_similarity_experiment():
    """任务3：相似度实验（8句子，3组近似+2个离群）"""
    print("\n" + "="*50)
    print("任务 3 · 相似度实验")
    print("="*50)
    
    # 准备 8 个句子（3 组近似 + 2 个离群）
    sentences = [
        # 组1：退款
        "如何申请退款",
        "退款流程是什么",
        "怎么办理退货",
        # 组2：发票
        "发票怎么开具",
        "发票抬头可以修改吗",
        # 组3：物流
        "订单什么时候发货",
        "物流信息在哪里查询",
        # 离群
        "今天天气不错",
        "晚上吃什么好",
    ]
    
    print("\n=== 1. 嵌入 8 个句子 ===")
    embed = get_embed_fn()
    vectors = embed(sentences)
    print(f"✓ 嵌入完成，维度: {len(vectors[0])}")
    
    # 1. 打印 8×8 相似度矩阵（保留 3 位小数）
    print("\n=== 2. 8×8 相似度矩阵 ===")
    matrix = similarity_matrix(vectors)
    
    # 打印表头
    header = "      " + "  ".join([f"S{i+1}" for i in range(8)])
    print(header)
    print("-" * len(header))
    
    for i, row in enumerate(matrix):
        row_str = f"S{i+1}   " + "  ".join([f"{v:.3f}" for v in row])
        print(row_str)
    
    # 2. 对每个句子找 top-3 近邻，人工判断"是否符合直觉"
    print("\n=== 3. Top-3 近邻分析 ===")
    counter_intuitive = []
    
    for i, sentence in enumerate(sentences):
        # 因为分组最小是为2个如果3个就必有反直觉
        neighbors = top_k(vectors[i], vectors, k=3)  # k=3 包含自己，取前2个真正的邻居
        
        print(f"\n句子 {i+1}: \"{sentence}\"")
        print("  Top-3 近邻（排除自己）：")
        
        # 排除自己（下标相同且相似度为1.0）
        real_neighbors = [(idx, score) for idx, score in neighbors if idx != i][:3]
        
        for rank, (idx, score) in enumerate(real_neighbors, 1):
            neighbor_sentence = sentences[idx]
            print(f"    {rank}. [{score:.3f}] \"{neighbor_sentence}\"")
            
            # 简单判断是否符合直觉（同组或离群组）
            # 组划分：0-2是退款组，3-4是发票组，5-6是物流组，7-8是离群组
            def get_group(idx):
                if idx <= 2: return "退款"
                elif idx <= 4: return "发票"
                elif idx <= 6: return "物流"
                else: return "离群"
            
            expected_group = get_group(i)
            actual_group = get_group(idx)
            
            # 离群词找离群词算合理，否则应该同组
            if expected_group != "离群" and actual_group != expected_group and actual_group != "离群":
                counter_intuitive.append({
                    "source": sentence,
                    "neighbor": neighbor_sentence,
                    "score": score,
                    "reason": f"期望{expected_group}组，实际{actual_group}组"
                })
    
    # 3. 记录 3 个"不符合直觉"的案例，分析原因
    print("\n=== 4. 反直觉案例分析 ===")
    if counter_intuitive:
        print(f"发现 {len(counter_intuitive)} 个潜在反直觉案例：")
        for i, case in enumerate(counter_intuitive[:3], 1):  # 只取前3个
            print(f"\n案例 {i}:")
            print(f"  源句: \"{case['source']}\"")
            print(f"  近邻: \"{case['neighbor']}\" (相似度: {case['score']:.3f})")
            print(f"  原因: {case['reason']}")
            print(f"  分析: ", end="")
            
            # 简单分析可能原因
            if abs(len(case['source']) - len(case['neighbor'])) > 10:
                print("长度差异过大，可能导致语义偏移")
            elif any(word in case['source'] for word in ["怎么", "如何", "什么"]) and \
                 any(word in case['neighbor'] for word in ["怎么", "如何", "什么"]):
                print("疑问词相似但主题不同，模型被句式误导")
            else:
                print("可能存在一词多义或领域词干扰")
    else:
        print("未发现明显的反直觉案例（或分组定义过于宽松）")
        print("建议：尝试更相似的句子对，或加入专业领域术语测试")
    
    print("\n" + "="*50)
    print("实验完成！请将以上结果与 day-11.md 中的'感觉表'对比")
    print("="*50)
    
    return True

if __name__ == "__main__":
    # 先运行任务2验证API连通性
    if test_embedding_api():
        print("\n" + "="*50)
        print("任务2 通过，继续任务3...")
        print("="*50)
        test_similarity_experiment()
    else:
        print("任务2 失败，请检查配置后重试")
        sys.exit(1)