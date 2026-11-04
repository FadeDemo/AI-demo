# 使用完整模块路径导入

本练习的命令行代码通过 `from rag_knowledge_base.document_loader import load_documents` 导入目录读取函数。完整路径同时说明了包名和包内模块名。

写成 `from document_loader import load_documents` 时，解释器会寻找顶层模块。核对磁盘目录结构，有助于确定正确的导入路径。
