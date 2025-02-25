extern "C" {
#include "libavformat/avformat.h"
#include "libswscale/swscale.h"
}

void GetVideoFrameThread(void* data) {
  VideoContext* pVideoCtx = static_cast<VideoContext*>(data);

  for (unsigned int i = 0; i < pVideoCtx->bufferSize; i++) {
    pVideoCtx->buffer[i].create(pVideoCtx->dstWidth, pVideoCtx->dstHeight);
  }

  int read = 0;

  AVPacket packet = {};
  AVFrame* pVideoFrame = av_frame_alloc();
  AVFrame* pFrameRGB = av_frame_alloc();
  pFrameRGB->width = pVideoCtx->dstWidth;
  pFrameRGB->height = pVideoCtx->dstHeight;
  pFrameRGB->format = AV_PIX_FMT_RGBA;
  int res = av_frame_get_buffer(pFrameRGB, 1);

  while (pVideoCtx->decoded < pVideoCtx->bufferSize && read == 0 &&
         window.isOpen()) {
    read = av_read_frame(pVideoCtx->pFormatCtx, &packet);

    if (packet.stream_index == pVideoCtx->videoStreamIndex) {
      int sent = avcodec_send_packet(pVideoCtx->pCodecCtx, &packet);
      int recieved = avcodec_receive_frame(pVideoCtx->pCodecCtx, pVideoFrame);

      if (sent == 0 && recieved == 0) {
        sws_scale(pVideoCtx->pImgConvertCtx, pVideoFrame->data,
                  pVideoFrame->linesize, 0, pVideoFrame->height,
                  pFrameRGB->data, pFrameRGB->linesize);

        pVideoCtx->buffer[pVideoCtx->decoded].update(pFrameRGB->data[0]);
        pVideoCtx->decoded++;
      }
    }

    av_packet_unref(&packet);
  }

  pVideoCtx->filled = true;

  while (read == 0 && window.isOpen()) {
    if (pVideoCtx->decoded - pVideoCtx->read < pVideoCtx->bufferSize) {
      read = av_read_frame(pVideoCtx->pFormatCtx, &packet);

      if (packet.stream_index == pVideoCtx->videoStreamIndex) {
        int sent = avcodec_send_packet(pVideoCtx->pCodecCtx, &packet);
        int recieved = avcodec_receive_frame(pVideoCtx->pCodecCtx, pVideoFrame);

        if (sent == 0 && recieved == 0) {
          sws_scale(pVideoCtx->pImgConvertCtx, pVideoFrame->data,
                    pVideoFrame->linesize, 0, pVideoFrame->height,
                    pFrameRGB->data, pFrameRGB->linesize);

          pVideoCtx->buffer[pVideoCtx->decoded % pVideoCtx->bufferSize].update(
              pFrameRGB->data[0]);
          pVideoCtx->decoded++;
        }
      }

      av_packet_unref(&packet);
    }
  }

  pVideoCtx->ended = true;

  av_frame_unref(pVideoFrame);
  av_frame_unref(pFrameRGB);
}

int main() {
  const char* WayMovie = "";
  RectangleShape Black(
      Vector2f((float)window.getSize().x, (float)window.getSize().y));
  Black.setFillColor(Color(0, 0, 0));
  window.clear(), window.draw(Black), window.display();

  AVFormatContext* pFormatCtx = avformat_alloc_context();

  if (avformat_open_input(&pFormatCtx, WayMovie, NULL, NULL) != 0)
    throw "cannot load video from file!";
  if (avformat_find_stream_info(pFormatCtx, NULL) < 0)
    throw "cannot find stream information!";

  unsigned int videoStreamIndex = -1, res = -1;

  AVCodecContext* pVideoCodecCtx = NULL;
  AVCodec* pVideoCodec = NULL;

  for (unsigned int i = 0; i < pFormatCtx->nb_streams; i++) {
    if (pFormatCtx->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
      videoStreamIndex = i;

      pVideoCodec =
          avcodec_find_decoder(pFormatCtx->streams[i]->codecpar->codec_id);
      if (pVideoCodec == NULL) {
        hrow "cannot find video codec";
      }

      pVideoCodecCtx = avcodec_alloc_context3(pVideoCodec);
      avcodec_parameters_to_context(pVideoCodecCtx,
                                    pFormatCtx->streams[i]->codecpar);

      if (pVideoCodec) {
        res = avcodec_open2(pVideoCodecCtx, pVideoCodec, NULL);
      }

      break;
    }
  }

  double fps = av_q2d(pFormatCtx->streams[videoStreamIndex]->r_frame_rate);

  if (videoStreamIndex == -1) {
    throw "cannot find video stream!";
  }
  if (res < 0) {
    throw "cannot open deocder!";
  }

  Texture* videoBuffer = new Texture[(size_t)fps];
  if (videoBuffer == NULL) {
    throw "cannot allocate memory";
  }

  SwsContext* pImgConvertCtx =
      sws_getContext(pVideoCodecCtx->coded_width, pVideoCodecCtx->coded_height,
                     pVideoCodecCtx->pix_fmt, 1920, 1080, AV_PIX_FMT_RGBA,
                     SWS_BICUBIC, NULL, NULL, NULL);

  VideoContext param = {};
  param.buffer = videoBuffer;
  param.bufferSize = (unsigned int)fps;
  param.filled = false;
  param.pFormatCtx = pFormatCtx;
  param.pCodecCtx = pVideoCodecCtx;
  param.pImgConvertCtx = pImgConvertCtx;
  param.dstWidth = 1920;
  param.dstHeight = 1080;
  param.ended = false;

  Sprite sprite = {};
  Event evnt = {};
  Clock clock = {};

  _beginthread(GetVideoFrameThread, 0, (void*)&param);
  while (!param.filled) Sleep(10);

  while (true) {
    if (clock.getElapsedTime().asMilliseconds() >= (1000 / fps)) {
      clock.restart();
      while (window.pollEvent(evnt)) {
        if (evnt.type == Event::Closed) window.close();
        if (evnt.type == Event::Resized) setPictureParam();
      }

      if (!window.isOpen() || param.read == param.decoded && param.ended) {
        break;
      }

      sprite.setTexture(videoBuffer[param.read % param.bufferSize]);
      window.clear(), window.draw(sprite), window.display();

      ++param.read;
    }
  }

  avformat_free_context(pFormatCtx);
  delete[] param.buffer;
  music.stop();
  return 0;
}
