import streamlit as st
import os
import subprocess
import time
import json

# バイト数を人間が見やすい単位（MBなど）に変換する関数
def get_file_size_str(file_size_bytes):
    return f"{file_size_bytes / (1024 * 1024):.2f} MB"

# 秒数を「●分●秒」または「●秒」の文字列に変換する関数
def format_time_str(seconds_float):
    total_seconds = int(seconds_float)
    if total_seconds >= 60:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}分 {seconds}秒"
    else:
        return f"{total_seconds}秒"

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

st.title("🎵 ラウドネスノーマライザー")
st.write("音量を均一化します。")

uploaded_file = st.file_uploader("音声ファイルを選択してください", type=["mp3", "m4a", "wav", "ogg", "flac"])

if uploaded_file is not None:
    st.success("ファイルを読み込みました！")
    
    input_size_bytes = uploaded_file.size
    input_size_str = get_file_size_str(input_size_bytes)
    
    input_ext = os.path.splitext(uploaded_file.name)[1]
    temp_check_path = f"temp_check{input_ext}"
    with open(temp_check_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    duration_seconds = get_audio_duration(temp_check_path)
    os.remove(temp_check_path)
    
    duration_str = f"{int(duration_seconds // 60)}分 {int(duration_seconds % 60)}秒" if duration_seconds > 0 else "解析不可"
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="元のファイルサイズ", value=input_size_str)
    with col2:
        st.metric(label="音声の長さ", value=duration_str)

    st.subheader("🛠️ 処理設定")
    
    target_lufs = st.slider("ターゲットラウドネス値 (LUFS)", min_value=-24, max_value=-9, value=-14, step=1)
    to_mono = st.checkbox("モノラル（1ch）に変換する", value=True)
    convert_to_mp3 = st.checkbox("MP3フォーマットに変換する", value=True)
    
    if convert_to_mp3:
        # 💡 【追加機能】ビットレート方式の選択（VBR or CBR）
        bitrate_type = st.radio(
            "ビットレート方式",
            options=["可変ビットレート (VBR) - 容量を効率的に節約", "固定ビットレート (CBR) - 互換性・配信仕様重視"],
            index=0
        )
        
        # 選択された方式に応じて、表示する設定メニューを切り替える
        if "可変ビットレート" in bitrate_type:
            quality_mode = st.selectbox(
                "音質・容量モード（VBR）",
                options=["最高音質 (約240-320kbps相当)", "高音質・標準 (約170-210kbps相当)", "容量優先・トーク向け (約120-150kbps相当)"],
                index=1,
                help="音の複雑さに合わせてデータ量を自動で増減させ、容量を劇的に節約します。"
            )
            if quality_mode == "最高音質 (約240-320kbps相当)":
                vbr_setting = "0"
                est_bitrate = 260
            elif quality_mode == "高音質・標準 (約170-210kbps相当)":
                vbr_setting = "4"
                est_bitrate = 190
            else:
                vbr_setting = "6"
                est_bitrate = 130
        else:
            # 固定ビットレート（CBR）の場合のメニュー
            cbr_bitrate = st.selectbox(
                "固定ビットレート（CBR値）",
                options=["320k", "256k", "192k", "128k"],
                index=0,
                help="常に指定したデータ量を維持します。特定の配信プラットフォームの規定に合わせる際に有効です。"
            )
            est_bitrate = int(cbr_bitrate.replace("k", ""))
            
        # 予測ファイルサイズの表示
        if duration_seconds > 0:
            predicted_mb = (duration_seconds * est_bitrate) / (8 * 1024)
            if to_mono: predicted_mb = predicted_mb * 0.6 if "可変" in bitrate_type else predicted_mb * 0.5
            st.info(f"📋 変換後の予想ファイルサイズ: **約 {predicted_mb:.2f} MB**")
    
    if "processing" not in st.session_state:
        st.session_state.processing = False

    if not st.session_state.processing:
        if st.button("🚀 処理を開始する", type="primary", key="start_btn"):
            st.session_state.processing = True
            st.rerun()
    else:
        st.button("⏳ 処理を実行中...", type="secondary", disabled=True, key="disabled_btn")
        
        status_box = st.empty()
        progress_bar = st.progress(0)
        
        start_time = time.time()
        
        # ステップ1: ファイル準備
        status_box.info("📥 1/3: サーバーにファイルを準備しています...")
        progress_bar.progress(15)
        
        input_path = f"temp_input{input_ext}"
        with open(input_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        output_path = "output_normalized.mp3" if convert_to_mp3 else f"output_normalized{input_ext}"
        
        # ステップ2: FFmpeg実行
        progress_bar.progress(40)
        
        filters = [f"loudnorm=I={target_lufs}:TP=-1.0:LRA=11"]
        if to_mono: filters.append("pan=mono|c0=0.5*c0+0.5*c1")
        filter_str = ",".join(filters)
        
        cmd = ["ffmpeg", "-i", input_path, "-af", filter_str, "-ar", "44100"]
        
        if convert_to_mp3:
            if "可変" in bitrate_type:
                # VBR用のFFmpegオプション (-q:a)
                cmd.extend(["-c:a", "libmp3lame", "-q:a", vbr_setting, "-map_metadata", "-1"])
            else:
                # CBR用のFFmpegオプション (-b:a)
                cmd.extend(["-c:a", "libmp3lame", "-b:a", cbr_bitrate, "-map_metadata", "-1"])
                
        cmd.extend([output_path, "-y"])
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            while process.poll() is None:
                elapsed = time.time() - start_time
                elapsed_str = format_time_str(elapsed)
                status_box.warning(f"⚙️ 2/3: 音声を解析・最適化中... [{elapsed_str}経過] (フリーズしていません)")
                time.sleep(1)
                
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd, stderr=process.stderr.read())
            
            # ステップ3: 完了処理
            elapsed_time = time.time() - start_time
            elapsed_time_str = format_time_str(elapsed_time)
            
            progress_bar.progress(100)
            status_box.success(f"✨ 全ての処理が完了しました！ (合計時間: {elapsed_time_str})")
            st.balloons()
            
            output_size_bytes = os.path.getsize(output_path)
            output_size_str = get_file_size_str(output_size_bytes)
            
            st.subheader("📊 処理結果")
            res_col1, res_col2 = st.columns(2)
            with res_col1:
                st.write(f"元のサイズ: **{input_size_str}**")
                st.write(f"処理時間: **{elapsed_time_str}**")
            with res_col2:
                st.write(f"変換後サイズ: **{output_size_str}**")
            
            with open(output_path, "rb") as file:
                st.download_button(
                    label="📥 最適化済み音声をダウンロード",
                    data=file,
                    file_name=f"light_{os.path.splitext(uploaded_file.name)[0]}.mp3" if convert_to_mp3 else f"light_{uploaded_file.name}",
                    mime="audio/mpeg" if convert_to_mp3 else "audio/octet-stream"
                )
                
        except Exception as e:
            st.error(f"❌ エラーが発生しました: {e}")
        finally:
            st.session_state.processing = False
            if os.path.exists(input_path): os.remove(input_path)
