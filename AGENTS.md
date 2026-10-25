# 1、每次添加新指令都要在D:\desktop\bot\mlcqqbot\scripts\create_command_panel.py和D:\desktop\bot\mlcqqbot\handlers\command_router.py里面注册,每次新加功能都需要在D:\desktop\bot\mlcqqbot\features下面新建功能文件夹，就算只有一个文件也要文件夹分类好，其他位置同理

# 2、修改大量内容的时候需要询问我

# 3、修改时要注意耦合度和鲁棒性

# 4、添加功能注意可读性，并在每个文件开头和每个函数开头写好注释

# 5、每次执行任务时需要在D:\desktop\bot\mlcqqbot\task.md里面给出这次任务的具体实现方案和预期效果，任务完成后在结尾标记完成，每次新任务只能在旧任务完成后继续，新任务如果检查到有已完成标记，则清空现有的，写入当前的任务具体实现方案和预期效果
