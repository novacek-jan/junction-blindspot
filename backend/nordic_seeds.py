"""Nordic seed investors for the snowball crawler (ids checked by name + website/address, see git history).

Finnish funds are crawled first (priority), then the rest of the Nordics. Funds also listed in funds.py
(Lifeline, Creandum, Northzone, Inventure) are crawled as full funds: portfolio AND their own rounds.
"""
NORDIC_SEED_FUNDS = {
    # name: (country, [entity ids])
    "Maki.vc": ("Finland", ["415bc278-6ed1-4973-a684-07a8b8c5d855", "8f0ff46d-d609-4ce0-b719-85f739b92ca3",
                            "3100c303-0795-4673-a04d-7e612b421eb4", "f8053251-7ca3-4547-8989-f5dafd52544f"]),
    "Icebreaker.vc": ("Finland", ["70fb3317-cd8c-4c52-aa86-66502789bce3"]),
    "Voima Ventures": ("Finland", ["1f973216-f1e5-4466-8409-da6608460c02", "8673db97-466e-4e7e-8417-a0ce1207bf9e",
                                   "72101d71-41bb-4d55-be11-03d1b003116f"]),
    "Superhero Capital": ("Finland", ["8f18dee5-e41b-4eaa-86e2-f03f1a846edc"]),
    "Butterfly Ventures": ("Finland", ["114c3c85-dcce-450a-8305-1bacb716aec1"]),
    "Tesi": ("Finland", ["df5be140-d50e-4e21-bb4f-d8f1e4ad3959"]),
    "EQT Ventures": ("Sweden", ["f3d72345-6e90-4a0d-ad5a-8b6a36eb500c", "ca5cb2d6-9802-4605-b009-aaaac432b24f",
                                "d6cf13e1-92ff-4567-bd72-30316f2498e5", "c8a71740-f8ac-4901-aca5-68bbec989cd7"]),
    "Industrifonden": ("Sweden", ["7684b497-6faa-4239-8344-597c42d95999"]),
    "byFounders": ("Denmark", ["20003112-87a9-4ac0-be1a-bc97efecf19e", "2e8b308a-dab0-4fe3-8348-4e3cf12ea949",
                               "58007305-ce10-4e37-ae38-cc01ba58853b", "48ef319c-988e-4256-a1ff-cbacd0d44cb2"]),
    "SEED Capital Denmark": ("Denmark", ["76ca4c6b-53bf-4f31-944d-fa7123495abe", "d0d4c2ec-14ed-475e-8696-ee9f79f29fc8",
                                         "e47d6abd-4951-4592-be57-990de4d90673"]),
    "PreSeed Ventures": ("Denmark", ["5a659016-bbca-4b37-a508-8513f050b843"]),
    "Investinor": ("Norway", ["1d695567-9d67-47d4-a3cf-fdd40ca59d39", "afefae81-6294-51ae-92f3-50ef8bf1f94a",
                              "d161d8d8-3d78-4491-867e-59ce8a983a3d"]),
}
# Crawled funds (funds.py) that seed the Nordic crawl as full funds, with their country.
NORDIC_CRAWLED_FUNDS = {"Lifeline Ventures": "Finland", "Inventure": "Finland", "Creandum": "Sweden",
                        "Northzone": "Sweden"}
