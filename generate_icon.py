import os
from PIL import Image, ImageDraw, ImageFilter

def create_bookshelf_icon(size=512):
    # 用 4 倍超採樣 (2048x2048) 繪製向量級精美細節，再平滑縮放至目標尺寸
    scale = 4
    W = size * scale
    H = size * scale
    
    # 建立畫布 (RGBA)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 1. 圓角矩形背景 (Squircle)
    margin = int(W * 0.05)
    radius = int(W * 0.22)
    bg_box = [margin, margin, W - margin, H - margin]
    
    # 背景微陰影
    shadow_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_img)
    shadow_box = [margin + int(W*0.01), margin + int(H*0.03), W - margin + int(W*0.01), H - margin + int(H*0.03)]
    shadow_draw.rounded_rectangle(shadow_box, radius=radius, fill=(0, 0, 0, 140))
    shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(radius=int(W * 0.03)))
    img = Image.alpha_composite(shadow_img, img)
    draw = ImageDraw.Draw(img)
    
    # 繪製背景本體：深邃極致黑鈦石墨漸層 (#1e2129 -> #101216)
    # 以垂直漸層填充圓角矩形
    bg_mask = Image.new("L", (W, H), 0)
    bg_mask_draw = ImageDraw.Draw(bg_mask)
    bg_mask_draw.rounded_rectangle(bg_box, radius=radius, fill=255)
    
    bg_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for y in range(margin, H - margin):
        ratio = (y - margin) / (H - 2 * margin)
        # 頂部 #232733 到 底部 #0e1014
        r = int(35 * (1 - ratio) + 14 * ratio)
        g = int(39 * (1 - ratio) + 16 * ratio)
        b = int(51 * (1 - ratio) + 20 * ratio)
        for x_line in [(margin, y, W - margin, y)]:
            ImageDraw.Draw(bg_layer).line(x_line, fill=(r, g, b, 255))
    
    img.paste(bg_layer, (0, 0), bg_mask)
    draw = ImageDraw.Draw(img)
    
    # 圓角微邊框亮線
    draw.rounded_rectangle(bg_box, radius=radius, outline=(60, 68, 88, 180), width=int(W * 0.008))
    
    # 2. 核心元素：立體展開的書籍 (Open Book)
    # 中心定位
    cx = W // 2
    cy = int(H * 0.53)
    bw = int(W * 0.38) # 半寬
    bh = int(H * 0.28) # 書頁高度
    
    # 書底外皮 (深緋紅陰影外皮)
    cover_drop = int(H * 0.04)
    cover_poly_left = [
        (cx - bw - int(W*0.02), cy - int(bh*0.65) + cover_drop),
        (cx - int(W*0.01), cy - int(bh*0.8) + cover_drop),
        (cx - int(W*0.01), cy + bh + cover_drop),
        (cx - bw - int(W*0.02), cy + int(bh*0.8) + cover_drop)
    ]
    cover_poly_right = [
        (cx + int(W*0.01), cy - int(bh*0.8) + cover_drop),
        (cx + bw + int(W*0.02), cy - int(bh*0.65) + cover_drop),
        (cx + bw + int(W*0.02), cy + int(bh*0.8) + cover_drop),
        (cx + int(W*0.01), cy + bh + cover_drop)
    ]
    draw.polygon(cover_poly_left, fill=(150, 10, 15, 255))
    draw.polygon(cover_poly_right, fill=(130, 8, 12, 255))
    
    # 書皮邊角高光裝飾
    draw.line([cover_poly_left[0], cover_poly_left[3]], fill=(220, 25, 30, 200), width=int(W*0.01))
    draw.line([cover_poly_right[1], cover_poly_right[2]], fill=(220, 25, 30, 200), width=int(W*0.01))
    
    # 3. 內頁層疊效果 (底層頁次)
    sub_page_shift = int(W * 0.015)
    for shift, alpha in [(sub_page_shift * 2, 100), (sub_page_shift, 160)]:
        # 左底頁
        lp = [
            (cx - bw + shift, cy - int(bh*0.68) + shift),
            (cx - int(W*0.01), cy - int(bh*0.78) + shift),
            (cx - int(W*0.01), cy + bh - int(shift*0.8)),
            (cx - bw + shift, cy + int(bh*0.78) - int(shift*0.8))
        ]
        draw.polygon(lp, fill=(180, 190, 205, alpha))
        # 右底頁
        rp = [
            (cx + int(W*0.01), cy - int(bh*0.78) + shift),
            (cx + bw - shift, cy - int(bh*0.68) + shift),
            (cx + bw - shift, cy + int(bh*0.78) - int(shift*0.8)),
            (cx + int(W*0.01), cy + bh - int(shift*0.8))
        ]
        draw.polygon(rp, fill=(160, 170, 185, alpha))

    # 4. 主書頁 (潔淨典雅珍珠白)
    main_lp = [
        (cx - bw, cy - int(bh*0.72)),
        (cx - int(W*0.012), cy - int(bh*0.82)),
        (cx - int(W*0.012), cy + bh),
        (cx - bw, cy + int(bh*0.78))
    ]
    draw.polygon(main_lp, fill=(248, 250, 252, 255)) # 珍珠亮白
    
    main_rp = [
        (cx + int(W*0.012), cy - int(bh*0.82)),
        (cx + bw, cy - int(bh*0.72)),
        (cx + bw, cy + int(bh*0.78)),
        (cx + int(W*0.012), cy + bh)
    ]
    draw.polygon(main_rp, fill=(236, 240, 246, 255)) # 微陰影右頁
    
    # 5. 書脊中線陰影
    draw.polygon([
        (cx - int(W*0.015), cy - int(bh*0.82)),
        (cx + int(W*0.015), cy - int(bh*0.82)),
        (cx + int(W*0.015), cy + bh + int(H*0.01)),
        (cx - int(W*0.015), cy + bh + int(H*0.01))
    ], fill=(40, 45, 55, 230))
    
    # 6. 書頁上的文字閱讀線 (營造電子書閱讀感)
    line_color_left = (200, 210, 225, 220)
    line_color_right = (185, 195, 210, 220)
    line_height = int(bh * 0.16)
    
    # 左頁 4 行線
    for i in range(4):
        ly = cy - int(bh*0.45) + i * line_height
        lx1 = cx - int(bw * 0.85)
        lx2 = cx - int(bw * 0.2) if i != 3 else cx - int(bw * 0.45) # 最後一行較短
        draw.line([(lx1, ly), (lx2, ly - int(bh*0.08))], fill=line_color_left, width=int(W*0.012))
        
    # 右頁 4 行線
    for i in range(4):
        ry = cy - int(bh*0.45) + i * line_height
        rx1 = cx + int(bw * 0.2)
        rx2 = cx + int(bw * 0.85) if i != 3 else cx + int(bw * 0.6)
        draw.line([(rx1, ry - int(bh*0.08)), (rx2, ry)], fill=line_color_right, width=int(W*0.012))

    # 7. 書籤緞帶 (優雅典雅 Acrobat Crimson & Gold 雙色飄帶)
    ribbon_w = int(W * 0.05)
    ribbon_x1 = cx - ribbon_w // 2
    ribbon_x2 = cx + ribbon_w // 2
    ribbon_top = cy - int(bh*0.92)
    ribbon_bot = cy + int(bh*1.15)
    
    ribbon_poly = [
        (ribbon_x1, ribbon_top),
        (ribbon_x2, ribbon_top),
        (ribbon_x2, ribbon_bot),
        (cx, ribbon_bot - int(H*0.03)), # 燕尾剪角
        (ribbon_x1, ribbon_bot)
    ]
    # 鮮紅 Acrobat 紅緞帶
    draw.polygon(ribbon_poly, fill=(235, 16, 0, 255))
    # 緞帶高光左緣
    draw.line([(ribbon_x1 + int(W*0.005), ribbon_top), (ribbon_x1 + int(W*0.005), ribbon_bot - int(H*0.015))], fill=(255, 100, 80, 220), width=int(W*0.005))
    # 緞帶頂部金色書夾扣
    clip_box = [cx - int(W*0.035), ribbon_top - int(H*0.015), cx + int(W*0.035), ribbon_top + int(H*0.015)]
    draw.rounded_rectangle(clip_box, radius=int(W*0.01), fill=(245, 158, 11, 255), outline=(251, 191, 36, 255), width=int(W*0.004))

    # 8. 頂部現代感科技光暈 (象徵數位電子書與智慧書櫃)
    spark_y = cy - int(bh * 1.12)
    draw.ellipse([cx - int(W*0.02), spark_y - int(W*0.02), cx + int(W*0.02), spark_y + int(W*0.02)], fill=(255, 230, 120, 255))
    draw.line([(cx, spark_y - int(H*0.04)), (cx, spark_y + int(H*0.04))], fill=(255, 240, 160, 200), width=int(W*0.006))
    draw.line([(cx - int(W*0.04), spark_y), (cx + int(W*0.04), spark_y)], fill=(255, 240, 160, 200), width=int(W*0.006))

    # 高畫質降採樣縮放回 512x512
    final_img = img.resize((size, size), Image.Resampling.LANCZOS)
    return final_img

if __name__ == "__main__":
    icon_512 = create_bookshelf_icon(512)
    os.makedirs("E:/AI_project/acrobat_bookshelf/assets_build", exist_ok=True)
    icon_512.save("E:/AI_project/acrobat_bookshelf/assets_build/app_icon_preview.png", "PNG")
    print("Preview icon saved successfully.")
