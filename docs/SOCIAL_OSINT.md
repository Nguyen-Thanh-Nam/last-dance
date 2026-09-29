# Phạm vi Social OSINT

| Nền tảng | Mức hỗ trợ hiện tại | Cách xác minh |
| --- | --- | --- |
| Facebook | nhập URL + `verification_evidence` + danh sách post công khai; fixture offline | backlink từ website hoặc quote manual |
| LinkedIn | nhập URL/JSON thủ công; không vượt đăng nhập | backlink và kiểm tra chéo |
| YouTube | fetch trang channel/video công khai nếu URL được cung cấp | URL, title và backlink |
| GitHub | fetch trang repository/profile công khai nếu URL được cung cấp | domain/README/link website |
| Instagram, TikTok, X, Threads, Reddit, Telegram, Discord, Zalo | nhập URL hoặc export công khai thủ công | reviewer kiểm tra permalink và backlink |
| Medium/blog | URL công khai/manual | domain và nội dung bài |

Collector không truy cập nhóm kín, không đăng nhập, không thu thập hồ sơ cá nhân không cần thiết và không giả lập API nền tảng. Với nền tảng chặn bot, source được ghi là `social_manual`, trạng thái `needs_review` nếu thiếu evidence. Cấu trúc input:

```json
{
  "platform": "facebook",
  "url": "https://facebook.com/acmerobotics",
  "handle": "acmerobotics",
  "verification_evidence": "The official website acme.example links to this page.",
  "posts": [{"permalink": "https://facebook.com/.../posts/1", "published_at": "2025-02-01T10:00:00Z", "content": "..."}]
}
```
