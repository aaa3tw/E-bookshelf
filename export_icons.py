import os
from pathlib import Path
from PIL import Image
from generate_icon import create_bookshelf_icon

def export_all_icons():
    base_dir = Path("E:/AI_project/acrobat_bookshelf").resolve()
    frontend_dir = base_dir / "frontend"
    assets_dir = frontend_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 產生高解析度主圖
    print("正在生成向量級 512x512 主圖...")
    icon_512 = create_bookshelf_icon(512)
    icon_192 = icon_512.resize((192, 192), Image.Resampling.LANCZOS)
    icon_64 = icon_512.resize((64, 64), Image.Resampling.LANCZOS)
    icon_32 = icon_512.resize((32, 32), Image.Resampling.LANCZOS)
    
    # 2. 儲存 Web 圖片
    icon_512.save(str(assets_dir / "icon.png"), "PNG")
    icon_512.save(str(assets_dir / "icon-512.png"), "PNG")
    icon_192.save(str(assets_dir / "icon-192.png"), "PNG")
    icon_32.save(str(assets_dir / "icon-32.png"), "PNG")
    print(f"已儲存 Web 圖標至: {assets_dir}")
    
    # 3. 儲存 Windows ICO 格式（內含 16, 24, 32, 48, 64, 128, 256 多解析度金字塔）
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_path_app = base_dir / "app_icon.ico"
    ico_path_fav = frontend_dir / "favicon.ico"
    
    icon_512.save(str(ico_path_app), format="ICO", sizes=ico_sizes)
    icon_512.save(str(ico_path_fav), format="ICO", sizes=ico_sizes)
    print(f"已儲存 Windows 應用程式圖標: {ico_path_app}")
    print(f"已儲存 Web Favicon: {ico_path_fav}")

if __name__ == "__main__":
    export_all_icons()
