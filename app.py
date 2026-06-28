import streamlit as st
import os
import subprocess
import time
import json

# バイト数を人間が見やすい単位（MBなど）に変換する関数
def get_file_size_str(file_size_bytes):
    return f"{file_size_bytes / (1024 * 1024):.2f} MB"

# 音声の長さ（秒）をffprobeで取得する関数
def get_audio_duration(file_path):
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except:
        return 0.0

# 画面のタイトルと説明
st.title("🎵 ラウドネスノーマライザー")
st.write("音量を均一化します。")

# 1. ファイルのアップロード欄
uploaded_file = st.file_uploader("音声ファイルを選択してください (m4a, mp3, wav など)", type=["mp3", "m4a", "wav", "ogg", "flac"])

if uploaded_file is not None:
    st.success("ファイルを読み込みました！")
    
    # --- 元ファイルの情報を表示 ---
    input_size_bytes = uploaded_file.size
    input_size_str = get_file_size_str(input_size_bytes)
    
    # 一時保存して長さを測る
    input_ext = os.path.splitext(uploaded_file.name)[1]
    temp_check_path = f"temp_check{input_ext}"
    with open(temp_check_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    duration_seconds = get_audio_duration(temp_check_path)
    os.remove(temp_check_path) # すぐ消す
    
    # 時間を分：秒にする
    duration_str = f"{int(duration_seconds // 60)}分 {int(duration_seconds % 60)}秒" if duration_seconds > 0 else "解析不可"
    
    # メタ情報表示
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="元のファイルサイズ", value=input_size_str)
    with col2:
        st.metric(label="音声の長さ", value=duration_str)

    # --- 設定エリア ---
    st.subheader("🛠️ 処理設定")
    
    target_lufs = st.slider(
        "ターゲットラウドネス値 (LUFS)", 
        min_value=-24, max_value=-9, value=-16, step=1,
        help="-14: YouTube/Apple Podcast, -16: Spotify/Amazon, -24: テレビ放送"
    )
    
    to_mono = st.checkbox("モノラル（1ch）に変換する", value=False, help="容量をさらに節約できます。")
    convert_to_mp3 = st.checkbox("MP3フォーマットに変換する", value=True)
    
    bitrate = "320k"
    if convert_to_mp3:
        bitrate = st.selectbox(
            "MP3 ビットレート",
            options=["320k", "256k", "192k", "128k"],
            index=0
        )
        
        # 【追加機能】変換前の容量の目安を計算して表示
        if duration_seconds > 0:
            bitrate_num = int(bitrate.replace("k", ""))
            # ビットレート(kbps)から容量(MB)を予測する式
            predicted_mb = (duration_seconds * bitrate_num) / (8 * 1024)
            # モノラルにする場合はさらに容量が半分近くになります（FFmpegのmp3圧縮特性）
            if to_mono:
                predicted_mb = predicted_mb * 0.65 # 実測値に近い補正値
            st.info(f"💡 変換後の予想ファイルサイズ: **約 {predicted_mb:.2f} MB**")
    
    # --- 変換実行エリア ---
    if st.button("🚀 処理を開始する", type="primary"):
        # プログレスバーと時間計測の準備
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        start_time = time.time() # 計測開始
        
        # 1. ファイル保存フェーズ
        status_text.text("1/3: サーバーにファイルを準備中...")
        progress_bar.progress(15)
        
        input_path = f"temp_input{input_ext}"
        with open(input_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        if convert_to_mp3:
            output_path = "output_normalized.mp3"
        else:
            output_path = f"output_normalized{input_ext}"
            
        # 2. FFmpeg処理フェーズ
        status_text.text("2/3: 音声を解析・ラウドネス調整中（ここが一番時間がかかります）...")
        progress_bar.progress(40)
        
        filters = [f"loudnorm=I={target_lufs}:TP=-1.0:LRA=11"]
        if to_mono:
            filters.append("pan=mono|c0=0.5*c0+0.5*c1")
        filter_str = ",".join(filters)
        
        cmd = ["ffmpeg", "-i", input_path, "-af", filter_str, "-ar", "48000"]
        if convert_to_mp3:
            cmd.extend(["-c:a", "libmp3lame", "-b:a", bitrate])
        cmd.extend([output_path, "-y"])
        
        try:
            # FFmpeg実行
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # 3. 完了フェーズ
            end_time = time.time() # 計測終了
            elapsed_time = end_time - start_time
            
            progress_bar.progress(100)
            status_text.text(f"✨ 処理完了！ (かかった時間: {elapsed_time:.1f} 秒)")
            st.balloons()
            
            # できあがったファイルサイズの取得
            output_size_bytes = os.path.getsize(output_path)
            output_size_str = get_file_size_str(output_size_bytes)
            
            # 結果表示
            st.subheader("📊 処理結果一覧")
            res_col1, res_col2 = st.columns(2)
            with res_col1:
                st.write(f"元のサイズ: **{input_size_str}**")
                st.write(f"処理時間: **{elapsed_time:.1f} 秒**")
            with res_col2:
                st.write(f"変換後サイズ: **{output_size_str}**")
            
            # ダウンロードボタン
            with open(output_path, "rb") as file:
                st.download_button(
                    label="📥 処理済み音声をダウンロード",
                    data=file,
                    file_name=f"normalized_{os.path.splitext(uploaded_file.name)[0]}{'.mp3' if convert_to_mp3 else input_ext}",
                    mime="audio/mpeg" if convert_to_mp3 else "audio/octet-stream"
                )
                
        except subprocess.CalledProcessError as e:
            st.error("❌ エラーが発生しました。")
            st.code(e.stderr)
            
        finally:
            # 掃除
            if os.path.exists(input_path): os.remove(input_path)
            if os.path.exists(output_path): os.remove(output_path)
