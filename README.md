# wnc

Test decode với runtime decode

# Xuất file requirements.txt
pip freeze > requirements.txt

# Xuất file requirements và packages
pip download -r requirements.txt -d packages

# Sau khi copy file requirements với folder packages sang máy khác thì cài
pip install --no-index --find-links=packages -r requirements.txt

# Tạo .exe
pyinstaller `
    --onefile `
    --windowed `
    --name GUI `
    --add-data "golden_label.png;." `
    --add-binary "D:/Travis/wnc/.venv/lib/site-packages/pylibdmtx/libdmtx-64.dll;pylibdmtx" `
    gui.py


# Các dữ liệu cần thay đổi theo model 
## main.py
1. template ảnh: "golden_h08.png"
2. các thông số dmx_dx, dmx_dy, dmx_w, dmx_h
3. row_tol trong sort_top_left: tolerance của việc sắp xếp
4. tighten_white(): nếu label mới có viền trắng, dày, mỏng, chỉnh margin để crop chính xác.

## gui.py
1. thư mục ảnh và kết quả:
"D:/project/raw_images"
"D:/project/result_images"
"D:/project/result_json"
Cách cải thiện:
Dùng config file / biến môi trường / dialog chọn thư mục → dễ deploy trên máy khác.
Ví dụ lưu trong self.save_folder và self.result_folder, hoặc QFileDialog.getExistingDirectory().
2. tham số dmx_dx=130, dmx_dy=90, dmx_w=90, dmx_h=90
3. thư mục cho camera: DualBaslerCamera(save_folder="D:/project/raw_images", concat_mode="v")
4. Nơi export CSV file. 
5. Có nên tự lưu 1 database để kiểm tra có bị trùng code trong ngày không?


