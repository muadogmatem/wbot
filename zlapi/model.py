# modules/model.py
from enum import Enum

class BinBankCard(Enum):
    """
    Danh sách BIN ngân hàng chính thức từ Zalo (cập nhật 2025)
    Dùng trực tiếp số BIN thay vì chuỗi tên → gửi thẻ cực kỳ ổn định, không bị lỗi do thay đổi tên hiển thị
    """
    ABBank                  = 970425
    ACB                     = 970416
    Agribank                = 970405
    BIDV                    = 970418
    BVBank                  = 970454
    BacA_Bank               = 970409
    BaoViet_Bank            = 970438
    CAKE                    = 546034
    CB_Bank                 = 970444
    CIMB_Bank               = 422589
    Coop_Bank               = 970446
    DBS_Bank                = 796500
    DongA_Bank              = 970406
    Eximbank                = 970431
    GPBank                  = 970408
    HDBank                  = 970437
    HSBC                    = 458761
    HongLeong_Bank          = 970442
    IBK_HCM                 = 970456
    IBK_HN                  = 970455
    Indovina_Bank           = 970434
    KBank                   = 668888
    KienlongBank            = 970452
    Kookmin_Bank_HCM        = 970463
    Kookmin_Bank_HN         = 970462
    LPBank                  = 970449
    MB_Bank                 = 970422
    MSB                     = 970426
    NCB                     = 970419
    Nam_A_Bank              = 970428
    NongHyup_Bank           = 801011
    OCB                     = 970448
    Ocean_Bank              = 970414
    PGBank                  = 970430
    PVcomBank               = 970412
    Public_Bank_Vietnam     = 970439
    SCB                     = 970429
    SHB                     = 970443
    Sacombank               = 970403
    Saigon_Bank             = 970400
    SeABank                 = 970440
    Shinhan_Bank            = 970424
    Standard_Chartered_Vietnam = 970410
    TNEX                    = 9704261
    TPBank                  = 970423
    Techcombank             = 970407
    Timo                    = 963388
    UBank                   = 546035
    United_Overseas_Bank_Vietnam = 970458
    VIB                     = 970441
    VPBank                  = 970432
    VRB                     = 970421
    VietABank               = 970427
    VietBank                = 970433
    Vietcombank             = 970436
    VietinBank              = 970415
    Woori_Bank              = 970457

# Mapping từ key người dùng gõ → BinBankCard (rất tiện và chính xác)
BANK_SHORT_TO_BIN = {
    "vcb": BinBankCard.Vietcombank,
    "vietcombank": BinBankCard.Vietcombank,

    "tcb": BinBankCard.Techcombank,
    "techcombank": BinBankCard.Techcombank,

    "mb": BinBankCard.MB_Bank,
    "mbbank": BinBankCard.MB_Bank,

    "acb": BinBankCard.ACB,

    "vib": BinBankCard.VIB,

    "tpb": BinBankCard.TPBank,
    "tpbank": BinBankCard.TPBank,

    "vtb": BinBankCard.VietinBank,
    "vietinbank": BinBankCard.VietinBank,

    "bidv": BinBankCard.BIDV,

    "agri": BinBankCard.Agribank,
    "agribank": BinBankCard.Agribank,

    "shb": BinBankCard.SHB,

    "vpb": BinBankCard.VPBank,
    "vpbank": BinBankCard.VPBank,

    "scb": BinBankCard.SCB,

    "ocb": BinBankCard.OCB,

    "msb": BinBankCard.MSB,

    "hdbank": BinBankCard.HDBank,

    "sacombank": BinBankCard.Sacombank,
    "stb": BinBankCard.Sacombank,

    "eximbank": BinBankCard.Eximbank,

    "lpb": BinBankCard.LPBank,
    "lpbank": BinBankCard.LPBank,

    "seabank": BinBankCard.SeABank,

    "bacabank": BinBankCard.BacA_Bank,
    "pvcombank": BinBankCard.PVcomBank,
    "vietbank": BinBankCard.VietBank,
    "namabank": BinBankCard.Nam_A_Bank,
    "ncb": BinBankCard.NCB,
    "abbank": BinBankCard.ABBank,
    "baoviet": BinBankCard.BaoViet_Bank,
    "kienlongbank": BinBankCard.KienlongBank,

    "cake": BinBankCard.CAKE,
    "ubank": BinBankCard.UBank,

    "momo": None,        # Không hỗ trợ gửi thẻ ngân hàng
    "zalopay": None,     # Không hỗ trợ gửi thẻ ngân hàng
}

# Tên hiển thị đẹp cho người dùng
BANK_DISPLAY_NAME = {
    BinBankCard.Vietcombank: "Vietcombank",
    BinBankCard.Techcombank: "Techcombank",
    BinBankCard.MB_Bank: "MB Bank",
    BinBankCard.ACB: "ACB",
    BinBankCard.VIB: "VIB",
    BinBankCard.TPBank: "TPBank",
    BinBankCard.VietinBank: "Vietinbank",
    BinBankCard.BIDV: "BIDV",
    BinBankCard.Agribank: "Agribank",
    BinBankCard.SHB: "SHB",
    BinBankCard.VPBank: "VPBank",
    BinBankCard.SCB: "SCB",
    BinBankCard.OCB: "OCB",
    BinBankCard.MSB: "MSB",
    BinBankCard.HDBank: "HDBank",
    BinBankCard.Sacombank: "Sacombank",
    BinBankCard.Eximbank: "Eximbank",
    BinBankCard.LPBank: "LPBank",
    BinBankCard.SeABank: "SeABank",
    BinBankCard.BacA_Bank: "Bac A Bank",
    BinBankCard.PVcomBank: "PVcomBank",
    BinBankCard.VietBank: "VietBank",
    BinBankCard.Nam_A_Bank: "Nam A Bank",
    BinBankCard.NCB: "NCB",
    BinBankCard.ABBank: "ABBank",
    BinBankCard.BaoViet_Bank: "BaoVietBank",
    BinBankCard.KienlongBank: "Kien Long Bank",
    BinBankCard.CAKE: "CAKE by VPBank",
    BinBankCard.UBank: "Ubank by VPBank",
}