"""
Name frequency banks for the synthetic Australian corpus.

Synthetically generated but realistic given-name and surname frequencies,
keyed by the cultural groups that make up the Australian population:

    ANGLO   CHINESE  INDIAN   VIETNAMESE  FILIPINO
    ARABIC  GREEK    ITALIAN  KOREAN      SE_ASIAN

ANGLO is the dominant group and carries the ordinary standard English name
stock found across Australia, the UK and the US.

Flatness rule: 1.5% max top-1, 10% max top-10. No single name may dominate,
or the matcher is solving a trivially skewed distribution instead of a
realistic one. This is why the ANGLO pools are deliberately large.

Every name here is ordinary reference data of the kind a census
name-frequency table carries. No real person is represented.
"""

from __future__ import annotations

# National default mix. Weights sum to exactly 1000.
NAME_GROUP_WEIGHTS: list[tuple[str, int]] = [
    ("ANGLO", 620),
    ("CHINESE", 70),
    ("INDIAN", 70),
    ("ITALIAN", 45),
    ("GREEK", 32),
    ("VIETNAMESE", 45),
    ("ARABIC", 40),
    ("FILIPINO", 30),
    ("KOREAN", 20),
    ("SE_ASIAN", 28),
]

# Regional profiles. Every group key must appear in every profile, and every
# profile sums to 1000 -- a missing key silently biases that region's draw.
# CITIES in banks_places.py tags each city with one of these five keys.
NAME_GROUP_WEIGHTS_BY_REGION: dict[str, list[tuple[str, int]]] = {
    "DEFAULT": NAME_GROUP_WEIGHTS,
    "METRO_SYDNEY": [
        # Highest diversity of the five profiles.
        ("ANGLO", 470), ("CHINESE", 110), ("INDIAN", 110), ("ITALIAN", 55),
        ("GREEK", 45), ("VIETNAMESE", 70), ("ARABIC", 75), ("FILIPINO", 30),
        ("KOREAN", 20), ("SE_ASIAN", 15),
    ],
    "METRO_MELBOURNE": [
        # High diversity, and Greek/Italian heavy relative to the rest.
        ("ANGLO", 480), ("CHINESE", 105), ("INDIAN", 90), ("ITALIAN", 85),
        ("GREEK", 75), ("VIETNAMESE", 70), ("ARABIC", 45), ("FILIPINO", 20),
        ("KOREAN", 15), ("SE_ASIAN", 15),
    ],
    "METRO_PERTH": [
        # Anglo-heavy, with a larger SE Asian and Filipino share.
        ("ANGLO", 650), ("CHINESE", 60), ("INDIAN", 75), ("ITALIAN", 40),
        ("GREEK", 20), ("VIETNAMESE", 30), ("ARABIC", 25), ("FILIPINO", 50),
        ("KOREAN", 15), ("SE_ASIAN", 35),
    ],
    "REGIONAL": [
        # Strongly Anglo.
        ("ANGLO", 820), ("CHINESE", 25), ("INDIAN", 30), ("ITALIAN", 30),
        ("GREEK", 15), ("VIETNAMESE", 20), ("ARABIC", 15), ("FILIPINO", 20),
        ("KOREAN", 10), ("SE_ASIAN", 15),
    ],
}

# Probability that a person's forename and surname are drawn from different
# groups, which is what a population with a substantial intermarriage rate
# actually looks like. Holding this at zero would make the group a free
# feature for the matcher and every "Mei O'Brien" would vanish from the
# corpus. 16% is in the band Australian intermarriage rates sit in.
CROSS_GROUP_RATE: float = 0.16

MALE_FORENAMES_BY_GROUP: dict[str, list[tuple[str, int]]] = {
    "ANGLO": [('James', 1000), ('John', 998), ('Robert', 996), ('Michael', 994), ('William', 992), ('David', 991), ('Richard', 989), ('Charles', 987), ('Joseph', 985), ('Thomas', 983), ('Christopher', 982), ('Daniel', 980), ('Paul', 978), ('Mark', 976), ('Donald', 974), ('George', 973), ('Kenneth', 971), ('Steven', 969), ('Edward', 967), ('Brian', 965), ('Ronald', 964), ('Anthony', 962), ('Kevin', 960), ('Jason', 958), ('Matthew', 956), ('Gary', 955), ('Timothy', 953), ('Larry', 951), ('Jeffrey', 949), ('Frank', 948), ('Scott', 946), ('Eric', 944), ('Stephen', 942), ('Andrew', 940), ('Raymond', 939), ('Gregory', 937), ('Joshua', 935), ('Jerry', 933), ('Dennis', 931), ('Walter', 930), ('Patrick', 928), ('Peter', 926), ('Harold', 924), ('Douglas', 922), ('Henry', 921), ('Carl', 919), ('Arthur', 917), ('Ryan', 915), ('Roger', 913), ('Joe', 912), ('Jack', 910), ('Albert', 908), ('Jonathan', 906), ('Justin', 905), ('Terry', 903), ('Gerald', 901), ('Keith', 899), ('Samuel', 897), ('Willie', 896), ('Ralph', 894), ('Lawrence', 892), ('Nicholas', 890), ('Roy', 888), ('Benjamin', 887), ('Bruce', 885), ('Brandon', 883), ('Adam', 881), ('Harry', 879), ('Fred', 878), ('Wayne', 876), ('Billy', 874), ('Steve', 872), ('Louis', 870), ('Jeremy', 869), ('Aaron', 867), ('Randy', 865), ('Howard', 863), ('Eugene', 862), ('Russell', 860), ('Bobby', 858), ('Victor', 856), ('Martin', 854), ('Ernest', 853), ('Phillip', 851), ('Craig', 849), ('Alan', 847), ('Shawn', 845), ('Clarence', 844), ('Sean', 842), ('Philip', 840), ('Todd', 838), ('Christian', 836), ('Johnny', 835), ('Abraham', 833), ('Adrian', 831), ('Aidan', 829), ('Alex', 827), ('Alexander', 826), ('Alfred', 824), ('Ashton', 822), ('Austin', 820), ('Avery', 818), ('Ayden', 817), ('Blake', 815), ('Bradley', 813), ('Brady', 811), ('Brantley', 810), ('Braxton', 808), ('Brayden', 806), ('Brendan', 804), ('Brody', 802), ('Caleb', 801), ('Cameron', 799), ('Caden', 797), ('Carter', 795), ('Carson', 793), ('Chase', 792), ('Cody', 790), ('Cole', 788), ('Colin', 786), ('Colton', 784), ('Connor', 783), ('Cooper', 781), ('Corbin', 779), ('Corey', 777), ('Dakota', 775), ('Dallas', 774), ('Damian', 772), ('Dawson', 770), ('Declan', 768), ('Derek', 767), ('Derrick', 765), ('Devin', 763), ('Dominic', 761), ('Donovan', 759), ('Dylan', 758), ('Easton', 756), ('Eli', 754), ('Elias', 752), ('Elijah', 750), ('Elliott', 749), ('Emmanuel', 747), ('Ethan', 745), ('Evan', 743), ('Ezra', 741), ('Felix', 740), ('Finn', 738), ('Forrest', 736), ('Franklin', 734), ('Gabriel', 732), ('Gage', 731), ('Garrett', 729), ('Gavin', 727), ('Grant', 725), ('Grayson', 724), ('Griffin', 722), ('Gunner', 720), ('Hayden', 718), ('Harrison', 716), ('Hudson', 715), ('Hugh', 713), ('Hunter', 711), ('Ian', 709), ('Isaac', 707), ('Isaiah', 706), ('Ivan', 704), ('Jackson', 702), ('Jacob', 700), ('Jaden', 698), ('Jake', 697), ('Jalen', 695), ('Jared', 693), ('Jaxson', 691), ('Jay', 689), ('Jayden', 688), ('Jaylen', 686), ('Jeff', 684), ('Jeremiah', 682), ('Jerome', 681), ('Jesse', 679), ('Jett', 677), ('Jimmy', 675), ('Jace', 673), ('Jonah', 672), ('Jonas', 670), ('Jordan', 668), ('Josiah', 666), ('Judah', 664), ('Jude', 663), ('Julian', 661), ('Kaden', 659), ('Kai', 657), ('Kaleb', 655), ('Kameron', 654), ('Karter', 652), ('Keegan', 650), ('Kelly', 648), ('Kelvin', 646), ('Kendrick', 645), ('Kieran', 643), ('Killian', 641), ('King', 639), ('Kobe', 637), ('Koda', 636), ('Kolton', 634), ('Kristian', 632), ('Kyle', 630), ('Kyree', 629), ('Lamar', 627), ('Lance', 625), ('Landen', 623), ('Landon', 621), ('Lane', 620), ('Lawson', 618), ('Layne', 616), ('Leon', 614), ('Leroy', 612), ('Levi', 611), ('Lewis', 609), ('Liam', 607), ('Lincoln', 605), ('Logan', 603), ('Lucas', 602), ('Lucian', 600), ('Luke', 598), ('Macon', 596), ('Maddox', 594), ('Makai', 593), ('Malcolm', 591), ('Malik', 589), ('Manual', 587), ('Marc', 586), ('Marcel', 584), ('Marcus', 582), ('Marlon', 580), ('Marquis', 578), ('Marshall', 577), ('Marvin', 575), ('Mason', 573), ('Mateo', 571), ('Maurice', 569), ('Max', 568), ('Maxwell', 566), ('Melvin', 564), ('Micah', 562), ('Miles', 560), ('Milo', 559), ('Milton', 557), ('Mitchell', 555), ('Monroe', 553), ('Morgan', 551), ('Moses', 550), ('Nash', 548), ('Nataniel', 546), ('Nathaniel', 544), ('Neal', 543), ('Neil', 541), ('Nelson', 539), ('Nick', 537), ('Oliver', 535), ('Dominick', 534), ('Rowan', 532), ('Ryder', 530), ('Ryker', 528), ('Rylan', 526), ('Tristan', 525), ('Tucker', 523), ('Tyler', 521), ('Tyson', 519), ('Uriah', 517), ('Vincent', 516), ('Waylon', 514), ('Wesley', 512), ('Weston', 510), ('Wyatt', 508), ('Xander', 507), ('Xavier', 505), ('Zachary', 503), ('Zane', 501), ('Zion', 500)],
    "CHINESE": [('Wei', 10), ('Jie', 10), ('Hao', 10), ('Yi', 10), ('Ming', 10), ('Hui', 10), ('Jian', 10), ('Bo', 10), ('Lei', 10), ('Xin', 10), ('Jun', 10), ('Ping', 10), ('Tao', 10), ('Qiang', 10), ('Cheng', 10), ('Bin', 10), ('Feng', 10), ('Hua', 10), ('Lin', 10), ('Dong', 10), ('Chao', 10), ('Peng', 10), ('Xiaoming', 10), ('Xiao', 10), ('Jianbo', 10), ('Junjie', 10), ('Zhaohui', 10), ('Xiaojian', 10), ('Zhigang', 10), ('Shijie', 10), ('Yong', 10), ('Xiaobo', 10), ('Zhiqiang', 10), ('Yufeng', 10), ('Jianming', 10), ('Xiaolong', 10), ('Zhiyuan', 10), ('Xiaohua', 10), ('Zhiwei', 10), ('Zhiping', 10), ('Zhijian', 10), ('Zhijun', 10), ('Xiaodong', 10), ('Xuefeng', 10), ('Xiaoping', 9)],
    "INDIAN": [('Rajesh', 10), ('Sanjay', 10), ('Sunil', 10), ('Ajay', 10), ('Anil', 10), ('Vijay', 10), ('Amit', 10), ('Manoj', 10), ('Rahul', 10), ('Vivek', 10), ('Prakash', 10), ('Ravi', 10), ('Mahesh', 10), ('Ashok', 10), ('Suresh', 10), ('Devendra', 10), ('Ramesh', 10), ('Dinesh', 10), ('Arvind', 10), ('Sandeep', 10), ('Tarun', 10), ('Kamal', 10), ('Sameer', 10), ('Pradeep', 10), ('Pramod', 10), ('Pravin', 10), ('Satish', 10), ('Deepak', 10), ('Manish', 10), ('Nitin', 10), ('Rakesh', 10), ('Roshan', 10), ('Harpreet', 10), ('Gurpreet', 10)],
    "VIETNAMESE": [('An', 10), ('Bao', 10), ('Binh', 10), ('Cuong', 10), ('Dat', 10), ('Duc', 10), ('Duy', 10), ('Hai', 10), ('Hieu', 10), ('Huy', 10), ('Khanh', 10), ('Long', 10), ('Minh', 10), ('Nam', 10), ('Nghia', 10), ('Phuc', 10), ('Quan', 10), ('Quang', 10), ('Son', 10), ('Tai', 10), ('Tam', 9), ('Thanh', 9), ('Thang', 9), ('Tien', 9), ('Toan', 9), ('Trung', 9), ('Tuan', 9), ('Tung', 9), ('Viet', 9), ('Vinh', 9), ('Bach', 9), ('Chien', 9), ('Cong', 9), ('Dung', 9), ('Giang', 9), ('Hoa', 9), ('Hoang', 9), ('Hung', 9), ('Khoa', 9), ('Kien', 9), ('Lam', 8), ('Loc', 8), ('Manh', 8), ('Nhat', 8), ('Phong', 8), ('Phu', 8), ('Sang', 8), ('Thai', 8), ('Thien', 8), ('Thinh', 8), ('Tho', 8), ('Tri', 8), ('Trong', 8), ('Truong', 8), ('Van', 8), ('Vu', 8), ('Xuan', 8), ('Dai', 8), ('Hao', 8), ('Khiem', 8)],
    "FILIPINO": [('Jose', 10), ('Juan', 10), ('Manuel', 10), ('Pedro', 10), ('Eduardo', 10), ('Luis', 10), ('Antonio', 10), ('Miguel', 10), ('Carlos', 10), ('Francisco', 10), ('Roberto', 10), ('Ricardo', 10), ('Ramon', 10), ('Mario', 10), ('Fernandez', 10), ('Jaime', 10), ('Rodrigo', 10), ('Fernando', 10), ('Tomas', 10), ('Renato', 10), ('Jun', 9), ('Boyet', 9), ('Resty', 9), ('Dodong', 9)],
    "ARABIC": [('Abdallah', 10), ('Adel', 10), ('Ahmad', 10), ('Ali', 10), ('Amer', 10), ('Amir', 10), ('Anwar', 10), ('Bassam', 10), ('Bilal', 10), ('Fadi', 10), ('Fares', 10), ('Farid', 10), ('Ghassan', 10), ('Habib', 10), ('Hadi', 10), ('Hamza', 10), ('Hassan', 10), ('Hussein', 10), ('Ibrahim', 10), ('Imad', 10), ('Issam', 9), ('Jamal', 9), ('Kamal', 9), ('Karim', 9), ('Khaled', 9), ('Mahmoud', 9), ('Malek', 9), ('Marwan', 9), ('Mazen', 9), ('Mohamad', 9), ('Mostafa', 9), ('Mounir', 9), ('Nabil', 9), ('Nader', 9), ('Naji', 9), ('Omar', 9), ('Osama', 9), ('Rabih', 9), ('Rami', 9), ('Rashid', 8), ('Riad', 8), ('Sami', 8), ('Samir', 8), ('Tarek', 8), ('Wael', 8), ('Walid', 8), ('Yasser', 8), ('Youssef', 8), ('Zaher', 8), ('Ziad', 8), ('Ayman', 8), ('Basel', 8), ('Elias', 8), ('Fouad', 8), ('Georges', 8), ('Nabih', 8), ('Raed', 8), ('Saeed', 8)],
    "GREEK": [('Anastasios', 10), ('Andreas', 10), ('Angelo', 10), ('Antonios', 10), ('Apostolos', 10), ('Athanasios', 10), ('Christos', 10), ('Damianos', 10), ('Dimitrios', 10), ('Efthymios', 10), ('Elias', 10), ('Emmanouil', 10), ('Evangelos', 10), ('Fotios', 10), ('Georgios', 10), ('Grigorios', 10), ('Haralambos', 10), ('Ilias', 9), ('Ioannis', 9), ('Kostas', 9), ('Kyriakos', 9), ('Lambros', 9), ('Lefteris', 9), ('Leonidas', 9), ('Manolis', 9), ('Michalis', 9), ('Miltiadis', 9), ('Nikolaos', 9), ('Nikos', 9), ('Panagiotis', 9), ('Pantelis', 9), ('Paraskevas', 9), ('Petros', 9), ('Polychronis', 9), ('Savvas', 8), ('Sotirios', 8), ('Spyridon', 8), ('Stavros', 8), ('Stefanos', 8), ('Stelios', 8), ('Taxiarchis', 8), ('Thanasis', 8), ('Theodoros', 8), ('Vasilios', 8), ('Yiannis', 8), ('Zisis', 8), ('Argyris', 8), ('Charalambos', 8), ('Dionysios', 8), ('Loukas', 8)],
    "ITALIAN": [('Alessandro', 10), ('Alfredo', 10), ('Angelo', 10), ('Antonio', 10), ('Bruno', 10), ('Carlo', 10), ('Carmelo', 10), ('Cosimo', 10), ('Damiano', 10), ('Daniele', 10), ('Dario', 10), ('Davide', 10), ('Domenico', 10), ('Emilio', 10), ('Enrico', 10), ('Ettore', 10), ('Fabio', 10), ('Federico', 10), ('Filippo', 10), ('Francesco', 9), ('Franco', 9), ('Gabriele', 9), ('Gaetano', 9), ('Giancarlo', 9), ('Gianni', 9), ('Gino', 9), ('Giovanni', 9), ('Giuseppe', 9), ('Leonardo', 9), ('Lorenzo', 9), ('Luca', 9), ('Luciano', 9), ('Luigi', 9), ('Marcello', 9), ('Marco', 9), ('Mario', 9), ('Massimo', 9), ('Matteo', 9), ('Maurizio', 8), ('Michele', 8), ('Nicola', 8), ('Paolo', 8), ('Pasquale', 8), ('Pietro', 8), ('Raffaele', 8), ('Renato', 8), ('Riccardo', 8), ('Roberto', 8), ('Salvatore', 8), ('Sergio', 8), ('Silvio', 8), ('Stefano', 8), ('Tommaso', 8), ('Umberto', 8), ('Vincenzo', 8), ('Vito', 8)],
    "KOREAN": [('Min-jun', 10), ('Seo-jun', 10), ('Do-yoon', 10), ('Ye-jun', 10), ('Si-woo', 10), ('Ha-joon', 10), ('Joo-won', 10), ('Ji-ho', 10), ('Ji-hu', 10), ('Jun-seo', 10), ('Gun-woo', 10), ('Hyun-woo', 10), ('Ji-hoon', 10), ('Sung-min', 10), ('Min-jae', 10), ('Dong-hyun', 10), ('Seung-min', 10), ('Jun-young', 10), ('Jae-won', 10), ('Sang-hoon', 10), ('Hyun-joo', 10), ('Yeong-ho', 10), ('Joon-ho', 10), ('Myung-ho', 10), ('Ki-tae', 10), ('Jung-ho', 10), ('Byung-chul', 10), ('Minjun', 10), ('Min Jun', 10), ('Jiho', 10), ('Jihoon', 10), ('Jiwon', 10), ('Sungmin', 10), ('Donghyun', 10)],
    "SE_ASIAN": [('Anan', 10), ('Chai', 10), ('Kittipong', 10), ('Narong', 10), ('Preecha', 10), ('Somchai', 10), ('Somsak', 10), ('Surasak', 10), ('Thanawat', 10), ('Wichai', 10), ('Apichart', 10), ('Boonchu', 10), ('Chaiwat', 10), ('Decha', 10), ('Kamon', 10), ('Nattapong', 10), ('Phaisan', 10), ('Prasit', 10), ('Sakda', 10), ('Suchart', 10), ('Suthep', 9), ('Weerachai', 9), ('Bora', 9), ('Chanthou', 9), ('Dara', 9), ('Kosal', 9), ('Rithy', 9), ('Samnang', 9), ('Sokha', 9), ('Sopheak', 9), ('Vuthy', 9), ('Chanda', 9), ('Piseth', 9), ('Rattanak', 9), ('Sovann', 9), ('Veasna', 9), ('Adi', 9), ('Agus', 9), ('Bambang', 9), ('Budi', 9), ('Dedi', 8), ('Eko', 8), ('Hendra', 8), ('Joko', 8), ('Rizal', 8), ('Slamet', 8), ('Wahyu', 8), ('Yusuf', 8), ('Azlan', 8), ('Faizal', 8), ('Hafiz', 8), ('Ismail', 8), ('Razak', 8), ('Shafiq', 8), ('Zulkifli', 8), ('Bounma', 8), ('Khamla', 8), ('Somphone', 8), ('Vilaysack', 8)],
}

FEMALE_FORENAMES_BY_GROUP: dict[str, list[tuple[str, int]]] = {
    "ANGLO": [('Mary', 1000), ('Patricia', 998), ('Linda', 996), ('Barbara', 995), ('Elizabeth', 993), ('Jennifer', 992), ('Susan', 990), ('Margaret', 989), ('Dorothy', 987), ('Lisa', 986), ('Nancy', 984), ('Karen', 982), ('Betty', 981), ('Helen', 979), ('Sandra', 978), ('Donna', 976), ('Carol', 975), ('Ruth', 973), ('Sharon', 972), ('Michelle', 970), ('Laura', 969), ('Sarah', 967), ('Kimberly', 965), ('Deborah', 964), ('Jessica', 962), ('Shirley', 961), ('Cynthia', 959), ('Angela', 958), ('Melissa', 956), ('Brenda', 955), ('Amy', 953), ('Anna', 952), ('Rebecca', 950), ('Virginia', 948), ('Kathleen', 947), ('Pamela', 945), ('Martha', 944), ('Debra', 942), ('Amanda', 941), ('Stephanie', 939), ('Carolyn', 938), ('Christine', 936), ('Marie', 934), ('Janet', 933), ('Catherine', 931), ('Frances', 930), ('Ann', 928), ('Joyce', 927), ('Diane', 925), ('Alice', 924), ('Julie', 922), ('Heather', 921), ('Teresa', 919), ('Doris', 917), ('Gloria', 916), ('Evelyn', 914), ('Jean', 913), ('Cheryl', 911), ('Mildred', 910), ('Katherine', 908), ('Joan', 907), ('Ashley', 905), ('Judith', 904), ('Rose', 902), ('Janice', 900), ('Kelly', 899), ('Nicole', 897), ('Judy', 896), ('Christina', 894), ('Kathy', 893), ('Theresa', 891), ('Beverly', 890), ('Denise', 888), ('Tammy', 886), ('Irene', 885), ('Jane', 883), ('Lori', 882), ('Rachel', 880), ('Marilyn', 879), ('Andrea', 877), ('Kathryn', 876), ('Louise', 874), ('Sara', 873), ('Anne', 871), ('Jacqueline', 869), ('Wanda', 868), ('Bonnie', 866), ('Julia', 865), ('Ruby', 863), ('Lois', 862), ('Tina', 860), ('Phyllis', 859), ('Norma', 857), ('Paula', 856), ('Diana', 854), ('Annie', 852), ('Lillian', 851), ('Emily', 849), ('Robin', 848), ('Peggy', 846), ('Crystal', 845), ('Gladys', 843), ('Rita', 842), ('Dawn', 840), ('Connie', 839), ('Florence', 837), ('Tracy', 835), ('Edna', 834), ('Tiffany', 832), ('Carmen', 831), ('Rosa', 829), ('Cindy', 828), ('Grace', 826), ('Wendy', 825), ('Victoria', 823), ('Edith', 821), ('Kim', 820), ('Sherry', 818), ('Sylvia', 817), ('Josephine', 815), ('Thelma', 814), ('Shannon', 812), ('Sheila', 811), ('Ethel', 809), ('Ellen', 808), ('Elaine', 806), ('Marjorie', 804), ('Carrie', 803), ('Charlotte', 801), ('Monica', 800), ('Esther', 798), ('Pauline', 797), ('Emma', 795), ('Juanita', 794), ('Anita', 792), ('Rhonda', 791), ('Hazel', 789), ('Amber', 787), ('Eva', 786), ('Debbie', 784), ('April', 783), ('Leslie', 781), ('Clara', 780), ('Lucille', 778), ('Jamie', 777), ('Joanne', 775), ('Eleanor', 773), ('Valerie', 772), ('Danielle', 770), ('Megan', 769), ('Alicia', 767), ('Suzanne', 766), ('Michele', 764), ('Gail', 763), ('Bertha', 761), ('Darlene', 760), ('Veronica', 758), ('Jill', 756), ('Erin', 755), ('Geraldine', 753), ('Lauren', 752), ('Cathy', 750), ('Joann', 749), ('Lorraine', 747), ('Lynn', 746), ('Sally', 744), ('Regina', 743), ('Erica', 741), ('Beatrice', 739), ('Dolores', 738), ('Bernice', 736), ('Audrey', 735), ('Yvonne', 733), ('Annette', 732), ('June', 730), ('Samantha', 729), ('Marion', 727), ('Dana', 726), ('Stacy', 724), ('Ana', 722), ('Renee', 721), ('Ida', 719), ('Vivian', 718), ('Roberta', 716), ('Holly', 715), ('Brittany', 713), ('Melanie', 712), ('Loretta', 710), ('Jeanette', 708), ('Laurie', 707), ('Katie', 705), ('Kristen', 704), ('Vanessa', 702), ('Alma', 701), ('Sue', 699), ('Elsie', 698), ('Beth', 696), ('Jeanne', 695), ('Vicki', 693), ('Carla', 691), ('Tara', 690), ('Rosemary', 688), ('Eileen', 687), ('Lucy', 685), ('Courtney', 684), ('Allison', 682), ('Bradley', 681), ('Paige', 679), ('Brooke', 678), ('Payton', 676), ('Taylor', 674), ('Mackenzie', 673), ('Bailey', 671), ('Jordan', 670), ('Morgan', 668), ('Kendall', 667), ('Avery', 665), ('Riley', 664), ('Sydney', 662), ('Peyton', 660), ('Aubrey', 659), ('Harper', 657), ('Quinn', 656), ('Reagan', 654), ('Finley', 653), ('Rowan', 651), ('Eden', 650), ('Charlie', 648), ('Sage', 647), ('Reese', 645), ('Emerson', 643), ('Emery', 642), ('Ariel', 640), ('Aspen', 639), ('Kinsley', 637), ('Harlow', 636), ('Sutton', 634), ('Sloane', 633), ('Ember', 631), ('Teagan', 630), ('Delaney', 628), ('Parker', 626), ('Lyla', 625), ('Nora', 623), ('Olivia', 622), ('Ava', 620), ('Sophia', 619), ('Isabella', 617), ('Mia', 616), ('Amelia', 614), ('Abigail', 613), ('Mila', 611), ('Ella', 609), ('Sofia', 608), ('Aria', 606), ('Scarlett', 605), ('Madison', 603), ('Luna', 602), ('Chloe', 600), ('Penelope', 599), ('Layla', 597), ('Zoey', 595), ('Lily', 594), ('Hannah', 592), ('Addison', 591), ('Ellie', 589), ('Stella', 588), ('Natalie', 586), ('Zoe', 585), ('Leah', 583), ('Violet', 582), ('Aurora', 580), ('Savannah', 578), ('Brooklyn', 577), ('Bella', 575), ('Claire', 574), ('Skylar', 572), ('Paisley', 571), ('Everly', 569), ('Caroline', 568), ('Nova', 566), ('Genesis', 565), ('Emilia', 563), ('Kennedy', 561), ('Maya', 560), ('Willow', 558), ('Naomi', 557), ('Aaliyah', 555), ('Elena', 554), ('Ariana', 552), ('Gabriella', 551), ('Madelyn', 549), ('Cora', 547), ('Serenity', 546), ('Autumn', 544), ('Adeline', 543), ('Hailey', 541), ('Gianna', 540), ('Isla', 538), ('Eliana', 537), ('Nevaeh', 535), ('Ivy', 534), ('Sadie', 532), ('Piper', 530), ('Lydia', 529), ('Alexa', 527), ('Delilah', 526), ('Arianna', 524), ('Kaylee', 523), ('Sophie', 521), ('Brielle', 520), ('Madeline', 518), ('Madeleine', 517), ('Abby', 515), ('Addilyn', 513), ('Adalynn', 512), ('Ainsley', 510), ('Alaina', 509), ('Alana', 507), ('Alina', 506), ('Alyssa', 504), ('Amaya', 503), ('Amira', 501), ('Aniya', 500)],
    "CHINESE": [('Fang', 10), ('Min', 10), ('Jing', 10), ('Ying', 10), ('Yan', 10), ('Xia', 10), ('Li', 10), ('Xue', 10), ('Lei', 10), ('Lin', 10), ('Yun', 10), ('Hong', 10), ('Hua', 10), ('Qing', 10), ('Ling', 10), ('Mei', 10), ('Jie', 10), ('Juan', 10), ('Wen', 10), ('Xin', 10), ('Qi', 10), ('Qiong', 10), ('Xiaoyan', 10), ('Xiaoli', 10), ('Xiaoling', 10), ('Xiaomin', 10), ('Xiaomei', 10), ('Xiaohong', 10), ('Xiaorong', 10), ('Xiaofang', 10), ('Xiaoying', 10), ('Xiaojuan', 10), ('Xiaojing', 10), ('Xiaojie', 10), ('Xiaolan', 10), ('Xiaohui', 9), ('Xiaofeng', 9), ('Xiaowei', 9), ('Xiaoxue', 9), ('Xiaoyun', 9), ('Xiaoting', 9)],
    "INDIAN": [('Pooja', 10), ('Neha', 10), ('Priya', 10), ('Aarti', 10), ('Kavita', 10), ('Sunita', 10), ('Manju', 10), ('Rekha', 10), ('Geeta', 10), ('Anjali', 10), ('Ritu', 10), ('Renu', 10), ('Meena', 10), ('Sarita', 10), ('Archana', 10), ('Kirti', 10), ('Shilpa', 10), ('Smriti', 10), ('Jyoti', 10), ('Preeti', 10), ('Divya', 10), ('Rashmi', 10), ('Swati', 10), ('Shweta', 10), ('Nisha', 10), ('Poonam', 10), ('Seema', 10), ('Neelu', 10), ('Sushma', 10), ('Shalu', 10), ('Renuka', 10), ('Kiran', 9), ('Nandini', 9)],
    "VIETNAMESE": [('Anh', 10), ('Bich', 10), ('Chi', 10), ('Dung', 10), ('Ha', 10), ('Hang', 10), ('Hanh', 10), ('Hien', 10), ('Hoa', 10), ('Hong', 10), ('Huong', 10), ('Lan', 10), ('Lien', 10), ('Linh', 10), ('Loan', 10), ('Mai', 10), ('My', 10), ('Nga', 10), ('Ngan', 10), ('Ngoc', 10), ('Nhung', 9), ('Oanh', 9), ('Phuong', 9), ('Quyen', 9), ('Thao', 9), ('Thu', 9), ('Thuy', 9), ('Trang', 9), ('Tuyet', 9), ('Uyen', 9), ('Van', 9), ('Xuan', 9), ('Yen', 9), ('Bao', 9), ('Cam', 9), ('Dao', 9), ('Diem', 9), ('Diep', 9), ('Giang', 9), ('Hoai', 9), ('Hue', 8), ('Khanh', 8), ('Kim', 8), ('Lam', 8), ('Le', 8), ('Ly', 8), ('Minh', 8), ('Nhi', 8), ('Nhu', 8), ('Phuc', 8), ('Quynh', 8), ('Suong', 8), ('Tam', 8), ('Thanh', 8), ('Thuan', 8), ('Tien', 8), ('Trinh', 8), ('Truc', 8), ('Tuyen', 8), ('Vy', 8)],
    "FILIPINO": [('Maria', 10), ('Ana', 10), ('Paz', 10), ('Luz', 10), ('Rosa', 10), ('Flora', 10), ('Carmelita', 10), ('Teresita', 10), ('Corazon', 10), ('Rosario', 10), ('Josefina', 10), ('Virginia', 10), ('Lourdes', 10), ('Gloria', 10), ('Estrella', 10), ('Lilia', 10), ('Milagros', 10), ('Aurora', 10), ('Estela', 10), ('Nenita', 10), ('Linda', 9), ('Chona', 9), ('Marites', 9), ('Inday', 9)],
    "ARABIC": [('Abir', 10), ('Aisha', 10), ('Amal', 10), ('Amani', 10), ('Amira', 10), ('Aya', 10), ('Basma', 10), ('Dalia', 10), ('Dina', 10), ('Fadia', 10), ('Farah', 10), ('Fatima', 10), ('Ghada', 10), ('Hala', 10), ('Hanan', 10), ('Huda', 10), ('Iman', 10), ('Jamila', 10), ('Jana', 10), ('Karima', 9), ('Khadija', 9), ('Lamia', 9), ('Layla', 9), ('Leen', 9), ('Lina', 9), ('Maha', 9), ('Manal', 9), ('Mariam', 9), ('Maya', 9), ('Mona', 9), ('Nada', 9), ('Nadia', 9), ('Nahla', 9), ('Najwa', 9), ('Nour', 9), ('Rana', 9), ('Randa', 9), ('Rasha', 8), ('Reem', 8), ('Rima', 8), ('Sahar', 8), ('Salma', 8), ('Samar', 8), ('Sana', 8), ('Sawsan', 8), ('Suha', 8), ('Wafa', 8), ('Yasmin', 8), ('Zahra', 8), ('Zeina', 8), ('Hiba', 8), ('Rania', 8), ('Souad', 8), ('Wissam', 8), ('Zainab', 8)],
    "GREEK": [('Agapi', 10), ('Aikaterini', 10), ('Alexandra', 10), ('Anastasia', 10), ('Angeliki', 10), ('Anthoula', 10), ('Argyro', 10), ('Aspasia', 10), ('Athanasia', 10), ('Chrysoula', 10), ('Despina', 10), ('Despoina', 10), ('Dimitra', 10), ('Efthymia', 10), ('Eftihia', 10), ('Eleni', 10), ('Elpida', 9), ('Evangelia', 9), ('Fotini', 9), ('Georgia', 9), ('Ioanna', 9), ('Irini', 9), ('Kalliopi', 9), ('Katerina', 9), ('Konstantina', 9), ('Kyriaki', 9), ('Magdalini', 9), ('Marina', 9), ('Nikoletta', 9), ('Olympia', 9), ('Panagiota', 9), ('Paraskevi', 9), ('Persephone', 8), ('Polyxeni', 8), ('Sofia', 8), ('Sotiria', 8), ('Stamatia', 8), ('Stavroula', 8), ('Thalia', 8), ('Theodora', 8), ('Vasiliki', 8), ('Voula', 8), ('Xanthippe', 8), ('Zoi', 8), ('Areti', 8), ('Ourania', 8), ('Panayiota', 8), ('Stella', 8)],
    "ITALIAN": [('Adriana', 10), ('Alessandra', 10), ('Angela', 10), ('Antonella', 10), ('Assunta', 10), ('Bianca', 10), ('Carla', 10), ('Carmela', 10), ('Caterina', 10), ('Chiara', 10), ('Claudia', 10), ('Concetta', 10), ('Cristina', 10), ('Daniela', 10), ('Elena', 10), ('Elisabetta', 10), ('Emilia', 10), ('Federica', 10), ('Filomena', 10), ('Francesca', 9), ('Gabriella', 9), ('Giovanna', 9), ('Giulia', 9), ('Giuseppina', 9), ('Grazia', 9), ('Ilaria', 9), ('Immacolata', 9), ('Lucia', 9), ('Luisa', 9), ('Manuela', 9), ('Marcella', 9), ('Margherita', 9), ('Mariangela', 9), ('Marisa', 9), ('Martina', 9), ('Nicoletta', 9), ('Paola', 9), ('Patrizia', 9), ('Rita', 8), ('Roberta', 8), ('Rosa', 8), ('Rosanna', 8), ('Sabrina', 8), ('Serena', 8), ('Silvana', 8), ('Silvia', 8), ('Simona', 8), ('Stefania', 8), ('Teresa', 8), ('Valentina', 8), ('Valeria', 8), ('Vincenza', 8), ('Agostina', 8), ('Loredana', 8), ('Nunzia', 8), ('Pierina', 8)],
    "KOREAN": [('Seo-yeon', 10), ('Seo-yun', 10), ('Ji-woo', 10), ('Seo-hyeon', 10), ('Ha-eun', 10), ('Ha-yoon', 10), ('Min-seo', 10), ('Ji-yoo', 10), ('Ji-min', 10), ('Chae-won', 10), ('Yoon-seo', 10), ('Su-ah', 10), ('Da-eun', 10), ('Eun-ji', 10), ('Ji-hye', 10), ('Min-ji', 10), ('Soo-jin', 10), ('Hyun-jung', 10), ('Eun-ju', 10), ('Mi-young', 10), ('Sun-young', 10), ('Jin-ah', 10), ('Soo-min', 10), ('Ha-neul', 10), ('Bo-ram', 10), ('Hye-jin', 10), ('Seoyeon', 10), ('Jiwoo', 10), ('Haeun', 10), ('Jiyoo', 10), ('Jimin', 10), ('Jihye', 10), ('Soojin', 10), ('Sumin', 10)],
    "SE_ASIAN": [('Kanya', 10), ('Malee', 10), ('Nittaya', 10), ('Pensri', 10), ('Siriporn', 10), ('Sunisa', 10), ('Suphan', 10), ('Wanida', 10), ('Apinya', 10), ('Duangjai', 10), ('Jintana', 10), ('Kulap', 10), ('Nareerat', 10), ('Orathai', 10), ('Pimchanok', 10), ('Ratana', 10), ('Sirinya', 10), ('Somjit', 9), ('Suda', 9), ('Wipada', 9), ('Bopha', 9), ('Chantha', 9), ('Sokhom', 9), ('Sophea', 9), ('Sreymom', 9), ('Thida', 9), ('Chanlina', 9), ('Leakhena', 9), ('Naree', 9), ('Sothea', 9), ('Sovannary', 9), ('Ayu', 9), ('Dewi', 9), ('Indah', 8), ('Lestari', 8), ('Ningsih', 8), ('Putri', 8), ('Rina', 8), ('Sari', 8), ('Siti', 8), ('Wati', 8), ('Aishah', 8), ('Nurul', 8), ('Suriani', 8), ('Zaiton', 8), ('Bounmy', 8), ('Khamphet', 8), ('Manivanh', 8), ('Phonesavanh', 8)],
}

SURNAMES_BY_GROUP: dict[str, list[tuple[str, int]]] = {
    "ANGLO": [('Smith', 1000), ('Wilson', 999), ('Williams', 998), ('Brown', 997), ('Taylor', 997), ('Anderson', 996), ('Thompson', 995), ('Jones', 995), ('Martin', 994), ('Wright', 993), ('Robinson', 993), ('Clark', 992), ('Walker', 991), ('Harris', 991), ('Scott', 990), ('Young', 989), ('King', 989), ('Baker', 988), ('Campbell', 987), ('Stewart', 987), ('Cameron', 986), ('Kerr', 985), ('Duncan', 985), ('Jackson', 984), ('White', 983), ('Lee', 983), ('Hall', 982), ('Allen', 981), ('Hill', 981), ('Adams', 980), ('Nelson', 979), ('Carter', 979), ('Mitchell', 978), ('Roberts', 977), ('Turner', 977), ('Phillips', 976), ('Parker', 975), ('Evans', 975), ('Edwards', 974), ('Collins', 973), ('Morris', 972), ('Rogers', 972), ('Reed', 971), ('Cook', 970), ('Morgan', 970), ('Bell', 969), ('Murphy', 968), ('Bailey', 968), ('Cooper', 967), ('Richardson', 966), ('Cox', 966), ('Howard', 965), ('Ward', 964), ('Peterson', 964), ('Gray', 963), ('James', 962), ('Watson', 962), ('Brooks', 961), ('Kelly', 960), ('Sanders', 960), ('Price', 959), ('Bennett', 958), ('Wood', 958), ('Barnes', 957), ('Ross', 956), ('Henderson', 956), ('Coleman', 955), ('Jenkins', 954), ('Perry', 954), ('Powell', 953), ('Long', 952), ('Patterson', 952), ('Hughes', 951), ('Washington', 950), ('Butler', 950), ('Simmons', 949), ('Foster', 948), ('Bryant', 947), ('Alexander', 947), ('Russell', 946), ('Griffin', 945), ('Hayes', 945), ('Myers', 944), ('Ford', 943), ('Hamilton', 943), ('Graham', 942), ('Sullivan', 941), ('Wallace', 941), ('Woods', 940), ('Cole', 939), ('West', 939), ('Jordan', 938), ('Owens', 937), ('Reynolds', 937), ('Fisher', 936), ('Ellis', 935), ('Harrison', 935), ('Gibson', 934), ('McDonald', 933), ('Marshall', 933), ('Murray', 932), ('Freeman', 931), ('Wells', 931), ('Webb', 930), ('Simpson', 929), ('Stevens', 929), ('Tucker', 928), ('Porter', 927), ('Hunter', 927), ('Hicks', 926), ('Crawford', 925), ('Henry', 925), ('Boyd', 924), ('Mason', 923), ('Kennedy', 922), ('Warren', 922), ('Dixon', 921), ('Burns', 920), ('Gordon', 920), ('Shaw', 919), ('Holmes', 918), ('Rice', 918), ('Robertson', 917), ('Hunt', 916), ('Black', 916), ('Daniels', 915), ('Palmer', 914), ('Mills', 914), ('Nichols', 913), ('Grant', 912), ('Knight', 912), ('Ferguson', 911), ('Rose', 910), ('Stone', 910), ('Hawkins', 909), ('Dunn', 908), ('Perkins', 908), ('Hudson', 907), ('Spencer', 906), ('Gardner', 906), ('Stephens', 905), ('Payne', 904), ('Pierce', 904), ('Berry', 903), ('Matthews', 902), ('Arnold', 902), ('Wagner', 901), ('Willis', 900), ('Ray', 900), ('Watkins', 899), ('Olson', 898), ('Carroll', 897), ('Snyder', 897), ('Hart', 896), ('Cunningham', 895), ('Bradley', 895), ('Lane', 894), ('Andrews', 893), ('Harper', 893), ('Fox', 892), ('Riley', 891), ('Armstrong', 891), ('Carpenter', 890), ('Weaver', 889), ('Greene', 889), ('Lawrence', 888), ('Elliott', 887), ('Sims', 887), ('Austin', 886), ('Peters', 885), ('Kelley', 885), ('Franklin', 884), ('Lawson', 883), ('Fields', 883), ('Ryan', 882), ('Schmidt', 881), ('Bowman', 881), ('Meyers', 880), ('Barton', 879), ('Bates', 879), ('Baxter', 878), ('Beal', 877), ('Becker', 877), ('Beckett', 876), ('Benson', 875), ('Bentley', 875), ('Bishop', 874), ('Blackwell', 873), ('Bolton', 872), ('Boone', 872), ('Bowen', 871), ('Bowers', 870), ('Boyle', 870), ('Bradford', 869), ('Bradshaw', 868), ('Brady', 868), ('Branch', 867), ('Brewer', 866), ('Bridges', 866), ('Briggs', 865), ('Brock', 864), ('Buchanan', 864), ('Buckley', 863), ('Burgess', 862), ('Burke', 862), ('Burton', 861), ('Bush', 860), ('Byers', 860), ('Byrd', 859), ('Caldwell', 858), ('Carlson', 858), ('Carr', 857), ('Carson', 856), ('Chambers', 856), ('Chandler', 855), ('Chapman', 854), ('Chase', 854), ('Christensen', 853), ('Clarke', 852), ('Clayton', 852), ('Clements', 851), ('Cleveland', 850), ('Cline', 850), ('Cobb', 849), ('Cochran', 848), ('Coffey', 847), ('Cohen', 847), ('Collier', 846), ('Combs', 845), ('Compton', 845), ('Connor', 844), ('Cooke', 843), ('Copeland', 843), ('Cross', 842), ('Cullen', 841), ('Curry', 841), ('Curtis', 840), ('Dalton', 839), ('Daniel', 839), ('Daugherty', 838), ('Davenport', 837), ('David', 837), ('Davidson', 836), ('Davis', 835), ('Dawson', 835), ('Day', 834), ('Dean', 833), ('Decker', 833), ('Dennis', 832), ('Dickson', 831), ('Donovan', 831), ('Douglas', 830), ('Downs', 829), ('Doyle', 829), ('Drake', 828), ('Durham', 827), ('Dyer', 827), ('Eaton', 826), ('Ellison', 825), ('Emerson', 825), ('English', 824), ('Erickson', 823), ('Estes', 822), ('Everett', 822), ('Ewing', 821), ('Farley', 820), ('Farmer', 820), ('Farrell', 819), ('Faulkner', 818), ('Ferrell', 818), ('Finch', 817), ('Fitzgerald', 816), ('Fleming', 816), ('Fletcher', 815), ('Flynn', 814), ('Foley', 814), ('Fowler', 813), ('Francis', 812), ('Frank', 812), ('Frazier', 811), ('French', 810), ('Frost', 810), ('Fuller', 809), ('Gaines', 808), ('Gallagher', 808), ('Garner', 807), ('Garrett', 806), ('Garrison', 806), ('Gates', 805), ('George', 804), ('Gibbs', 804), ('Gilbert', 803), ('Giles', 802), ('Gill', 802), ('Gillespie', 801), ('Gilmore', 800), ('Glass', 800), ('Glenn', 799), ('Glover', 798), ('Goff', 797), ('Good', 797), ('Goodman', 796), ('Goodwin', 795), ('Gould', 795), ('Graves', 794), ('Green', 793), ('Greer', 793), ('Gregory', 792), ('Griffith', 791), ('Grimes', 791), ('Gross', 790), ('Hale', 789), ('Haley', 789), ('Halstead', 788), ('Hammond', 787), ('Hampton', 787), ('Hancock', 786), ('Hansen', 785), ('Hanson', 785), ('Hardin', 784), ('Harding', 783), ('Hardy', 783), ('Harmon', 782), ('Harrington', 781), ('Harvey', 781), ('Hastings', 780), ('Hatch', 779), ('Hayden', 779), ('Haynes', 778), ('Hays', 777), ('Heath', 777), ('Hebert', 776), ('Hendricks', 775), ('Hendrix', 775), ('Hensley', 774), ('Herman', 773), ('Herring', 772), ('Hess', 772), ('Hester', 771), ('Hickman', 770), ('Higgins', 770), ('Hines', 769), ('Hinton', 768), ('Hobbs', 768), ('Hodge', 767), ('Hodges', 766), ('Hoffman', 766), ('Hogan', 765), ('Holcomb', 764), ('Holden', 764), ('Holland', 763), ('Holloway', 762), ('Holt', 762), ('Hoover', 761), ('Hopkins', 760), ('Horn', 760), ('Horne', 759), ('Horton', 758), ('House', 758), ('Houston', 757), ('Howell', 756), ('Hubbard', 756), ('Huber', 755), ('Hull', 754), ('Humphrey', 754), ('Hurley', 753), ('Hurst', 752), ('Hutchins', 752), ('Hutchinson', 751), ('Hyde', 750), ('Ingram', 750), ('Irwin', 749), ('Jacobs', 748), ('Jacobson', 747), ('Jarvis', 747), ('Jefferson', 746), ('Jennings', 745), ('Jensen', 745), ('Johns', 744), ('Johnson', 743), ('Johnston', 743), ('Joseph', 742), ('Joyce', 741), ('Kane', 741), ('Kaufman', 740), ('Keith', 739), ('Keller', 739), ('Kemp', 738), ('Kent', 737), ('Key', 737), ('Kidd', 736), ('Kim', 735), ('Kinney', 735), ('Kirby', 734), ('Kirk', 733), ('Klein', 733), ('Kline', 732), ('Knapp', 731), ('Knowles', 731), ('Knox', 730), ('Koch', 729), ('Kramer', 729), ('Lamb', 728), ('Lambert', 727), ('Lancaster', 727), ('Landry', 726), ('Lang', 725), ('Langley', 725), ('Larsen', 724), ('Larson', 723), ('Leach', 722), ('Leonard', 722), ('Lester', 721), ('Lewis', 720), ('Lindsay', 720), ('Lindsey', 719), ('Little', 718), ('Livingston', 718), ('Lloyd', 717), ('Logan', 716), ('Love', 716), ('Lowe', 715), ('Lucas', 714), ('Lynch', 714), ('Lynn', 713), ('Lyons', 712), ('Macdonald', 712), ('Mack', 711), ('Madden', 710), ('Maddox', 710), ('Malone', 709), ('Mann', 708), ('Manning', 708), ('Marks', 707), ('Marsh', 706), ('Massey', 706), ('Mathews', 705), ('Mathis', 704), ('Maxwell', 704), ('May', 703), ('Mayer', 702), ('Maynard', 702), ('Mayo', 701), ('Mays', 700), ('Mcbride', 700), ('Mccall', 699), ('Mccarthy', 698), ('Mccarty', 697), ('Mcclain', 697), ('Mcclure', 696), ('Mcconnell', 695), ('Mccormick', 695), ('Mccoy', 694), ('Mccullough', 693), ('Mcdaniel', 693), ('Mcdonald', 692), ('Mcdowell', 691), ('Mcfadden', 691), ('Mcgee', 690), ('Mcintyre', 689), ('Mckay', 689), ('Mckee', 688), ('Mckenzie', 687), ('Mckinney', 687), ('Mcknight', 686), ('Mclaughlin', 685), ('Mclean', 685), ('Mcleod', 684), ('Mcmahon', 683), ('Mcmillan', 683), ('Mcneil', 682), ('Mcpherson', 681), ('Mcrae', 681), ('Meadows', 680), ('Melton', 679), ('Mercer', 679), ('Merrill', 678), ('Merritt', 677), ('Meyer', 677), ('Michaels', 676), ('Middleton', 675), ('Miles', 675), ('Miller', 674), ('Monroe', 673), ('Montgomery', 672), ('Moody', 672), ('Moon', 671), ('Mooney', 670), ('Moore', 670), ('Moran', 669), ('Moreland', 668), ('Morin', 668), ('Morrison', 667), ('Morrow', 666), ('Morse', 666), ('Morton', 665), ('Moses', 664), ('Mosley', 664), ('Moss', 663), ('Moyer', 662), ('Mueller', 662), ('Mullen', 661), ('Mullins', 660), ('Nash', 660), ('Neal', 659), ('Neil', 658), ('Newman', 658), ('Newton', 657), ('Nicholson', 656), ('Nielsen', 656), ('Nixon', 655), ('Noble', 654), ('Noel', 654), ('Noland', 653), ('Norman', 652), ('Norris', 652), ('North', 651), ('Norton', 650), ('Novak', 650), ("O'brien", 649), ("O'connor", 648), ("O'donnell", 647), ("O'neal", 647), ("O'neill", 646), ('Odom', 645), ('Oliver', 645), ('Olsen', 644), ('Orr', 643), ('Osborn', 643), ('Osborne', 642), ('Osgood', 641), ('Owen', 641), ('Pace', 640), ('Page', 639), ('Park', 639), ('Parks', 638), ('Parrish', 637), ('Parsons', 637), ('Pate', 636), ('Patrick', 635), ('Patton', 635), ('Paul', 634), ('Pearson', 633), ('Peck', 633), ('Pennington', 632), ('Petersen', 631), ('Petty', 631), ('Phelps', 630), ('Pickett', 629), ('Pittman', 629), ('Pitts', 628), ('Pollard', 627), ('Poole', 627), ('Pope', 626), ('Potter', 625), ('Potts', 625), ('Powers', 624), ('Pratt', 623), ('Preston', 622), ('Prince', 622), ('Proctor', 621), ('Pruitt', 620), ('Pugh', 620), ('Purcell', 619), ('Quinn', 618), ('Ramsey', 618), ('Randall', 617), ('Randolph', 616), ('Rasmussen', 616), ('Ratliff', 615), ('Raymond', 614), ('Reese', 614), ('Reeves', 613), ('Reid', 612), ('Reilly', 612), ('Rhodes', 611), ('Rich', 610), ('Richard', 610), ('Richards', 609), ('Richmond', 608), ('Riddle', 608), ('Riggs', 607), ('Roach', 606), ('Robbins', 606), ('Roberson', 605), ('Rodgers', 604), ('Rollins', 604), ('Roman', 603), ('Roth', 602), ('Rowe', 602), ('Rowland', 601), ('Roy', 600), ('Rush', 600), ('Russo', 599), ('Rutledge', 598), ('Sampson', 597), ('Sanford', 597), ('Sargent', 596), ('Saunders', 595), ('Savage', 595), ('Sawyer', 594), ('Schaefer', 593), ('Schmitt', 593), ('Schneider', 592), ('Schroeder', 591), ('Schultz', 591), ('Schwartz', 590), ('Sears', 589), ('Sellers', 589), ('Sexton', 588), ('Shaffer', 587), ('Shannon', 587), ('Sharp', 586), ('Sharpe', 585), ('Shelton', 585), ('Shepard', 584), ('Shepherd', 583), ('Sheppard', 583), ('Sherman', 582), ('Shields', 581), ('Short', 581), ('Shultz', 580), ('Simon', 579), ('Sinclair', 579), ('Singleton', 578), ('Skinner', 577), ('Slater', 577), ('Sloan', 576), ('Small', 575), ('Snider', 575), ('Snow', 574), ('Solomon', 573), ('Sparks', 572), ('Spears', 572), ('Spence', 571), ('Stafford', 570), ('Stanley', 570), ('Stanton', 569), ('Stark', 568), ('Starr', 568), ('Steele', 567), ('Stein', 566), ('Stephenson', 566), ('Stevenson', 565), ('Stokes', 564), ('Stout', 564), ('Strickland', 563), ('Strong', 562), ('Stuart', 562), ('Summers', 561), ('Sutton', 560), ('Swanson', 560), ('Sweeney', 559), ('Sweet', 558), ('Sykes', 558), ('Talley', 557), ('Tanner', 556), ('Tate', 556), ('Terrell', 555), ('Terry', 554), ('Thomas', 554), ('Thornton', 553), ('Thorpe', 552), ('Tillman', 552), ('Todd', 551), ('Townsend', 550), ('Travis', 550), ('Tyler', 549), ('Tyson', 548), ('Underwood', 547), ('Valentine', 547), ('Vance', 546), ('Vaughan', 545), ('Vaughn', 545), ('Venable', 544), ('Vernon', 543), ('Vickers', 543), ('Vincent', 542), ('Vinson', 541), ('Wade', 541), ('Wall', 540), ('Waller', 539), ('Walls', 539), ('Walsh', 538), ('Walter', 537), ('Walters', 537), ('Walton', 536), ('Warner', 535), ('Waters', 535), ('Watts', 534), ('Weber', 533), ('Webster', 533), ('Weeks', 532), ('Welch', 531), ('Welsh', 531), ('Weston', 530), ('Wheeler', 529), ('Whitaker', 529), ('Whitehead', 528), ('Whitfield', 527), ('Whitley', 527), ('Whitney', 526), ('Wiggins', 525), ('Wilcox', 525), ('Wilder', 524), ('Wiley', 523), ('Wilkerson', 522), ('Wilkins', 522), ('Wilkinson', 521), ('William', 520), ('Williamson', 520), ('Winchester', 519), ('Winters', 518), ('Wise', 518), ('Witt', 517), ('Wolf', 516), ('Wolfe', 516), ('Woodard', 515), ('Woodward', 514), ('Wooten', 514), ('Workman', 513), ('Wyatt', 512), ('Wynn', 512), ('Yates', 511), ('Yoder', 510), ('York', 510), ('Zimmerman', 509), ('McGregor', 508), ('McLeod', 508), ('MacDonald', 507), ('MacLean', 506), ('McIntyre', 506), ('McLaren', 505), ("O'Neill", 504), ("O'Connor", 504), ("O'Brien", 503), ("O'Sullivan", 502), ("O'Donnell", 502), ("O'Reilly", 501), ('Doherty', 500), ('Daly', 500)],
    "CHINESE": [('Wang', 10), ('Li', 10), ('Zhang', 10), ('Liu', 10), ('Chen', 10), ('Yang', 10), ('Huang', 10), ('Zhao', 10), ('Wu', 10), ('Zhou', 10), ('Xu', 10), ('Sun', 10), ('Ma', 10), ('Zhu', 10), ('Hu', 10), ('Guo', 10), ('Lin', 10), ('He', 10), ('Gao', 10), ('Liang', 10), ('Zheng', 10), ('Luo', 10), ('Song', 10), ('Xie', 10), ('Tang', 10), ('Han', 10), ('Cao', 10), ('Deng', 10), ('Xiao', 10), ('Feng', 10), ('Cheng', 10), ('Cai', 10), ('Yuan', 10), ('Yu', 10), ('Hong', 10), ('Pan', 10), ('Duan', 10), ('Lei', 10), ('Hou', 10), ('Shen', 10), ('Xiong', 10), ('Jin', 10), ('Zhong', 10), ('Yan', 10), ('Wei', 9)],
    "INDIAN": [('Patel', 10), ('Singh', 10), ('Sharma', 10), ('Kumar', 10), ('Das', 10), ('Gupta', 10), ('Reddy', 10), ('Desai', 10), ('Rao', 10), ('Joshi', 10), ('Nair', 10), ('Menon', 10), ('Iyer', 10), ('Pillai', 10), ('Varma', 10), ('Ranganathan', 10), ('Krishnan', 10), ('Raman', 10), ('Sen', 10), ('Bose', 10), ('Ghosh', 10), ('Banerjee', 10), ('Chatterjee', 10), ('Mukherjee', 10), ('Basu', 10), ('Dutt', 10), ('Chowdhury', 10), ('Ahluwalia', 10), ('Chopra', 10), ('Kapoor', 10), ('Khanna', 10), ('Malhotra', 10), ('Mehra', 10), ('Seth', 10), ('Bedi', 9), ('Dhillon', 9), ('Gill', 9), ('Kaur', 9), ('Sidhu', 9)],
    "VIETNAMESE": [('Nguyen', 10), ('Tran', 10), ('Le', 10), ('Pham', 10), ('Hoang', 10), ('Huynh', 10), ('Phan', 10), ('Vu', 10), ('Vo', 10), ('Dang', 10), ('Bui', 10), ('Do', 10), ('Ho', 10), ('Ngo', 10), ('Duong', 10), ('Ly', 10), ('Truong', 10), ('Dinh', 10), ('Lam', 10), ('Mai', 10), ('Trinh', 9), ('Doan', 9), ('Ta', 9), ('Cao', 9), ('Chu', 9), ('Dao', 9), ('Ha', 9), ('Luong', 9), ('Quach', 9), ('Thai', 9), ('Vuong', 9), ('Banh', 9), ('Chau', 9), ('Chung', 9), ('Dam', 9), ('Dieu', 9), ('Giang', 9), ('Kieu', 9), ('Lai', 9), ('Lieu', 9), ('Luu', 8), ('Nghiem', 8), ('Nong', 8), ('Phung', 8), ('Quan', 8), ('Son', 8), ('Tang', 8), ('Thach', 8), ('Tieu', 8), ('To', 8), ('Ton', 8), ('Tong', 8), ('Trieu', 8), ('Tu', 8), ('Ung', 8), ('Vien', 8), ('Vy', 8), ('Bach', 8), ('Diep', 8), ('Khuu', 8)],
    "FILIPINO": [('Santos', 10), ('Reyes', 10), ('Cruz', 10), ('Bautista', 10), ('Ocampo', 10), ('Garcia', 10), ('Mendoza', 10), ('Torres', 10), ('Villanueva', 10), ('Navarro', 10), ('Ramos', 10), ('Aquino', 10), ('Pineda', 10), ('Castro', 10), ('Dela Cruz', 10), ('Roxas', 10), ('Tolentino', 10), ('Fernandez', 10), ('Gomez', 10), ('Salazar', 10), ('Dizon', 10), ('Angeles', 10), ('Cortez', 10), ('Javier', 10), ('Gonzales', 10), ('Manalo', 10), ('David', 10), ('Ilagan', 9), ('Valencia', 9)],
    "ARABIC": [('Abboud', 10), ('Abdallah', 10), ('Abdo', 10), ('Ahmad', 10), ('Ali', 10), ('Amin', 10), ('Antoun', 10), ('Aoun', 10), ('Arida', 10), ('Assaf', 10), ('Attieh', 10), ('Awad', 10), ('Ayoub', 10), ('Azar', 10), ('Chahine', 10), ('Daher', 10), ('Dagher', 10), ('Darwiche', 10), ('El-Masri', 10), ('Fahd', 10), ('Farah', 9), ('Ghosn', 9), ('Habib', 9), ('Haddad', 9), ('Hage', 9), ('Hamdan', 9), ('Hanna', 9), ('Harb', 9), ('Hassan', 9), ('Hayek', 9), ('Issa', 9), ('Jaber', 9), ('Kanaan', 9), ('Karam', 9), ('Kassem', 9), ('Khalil', 9), ('Khoury', 9), ('Maalouf', 9), ('Mansour', 9), ('Moussa', 9), ('Nader', 8), ('Najjar', 8), ('Nasser', 8), ('Rahme', 8), ('Saad', 8), ('Sabbagh', 8), ('Salem', 8), ('Salloum', 8), ('Sarkis', 8), ('Sayegh', 8), ('Shaheen', 8), ('Sleiman', 8), ('Tannous', 8), ('Youssef', 8), ('Zakhour', 8), ('Zeidan', 8), ('Baz', 8), ('Chidiac', 8), ('Merhi', 8), ('Rizk', 8)],
    "GREEK": [('Alexopoulos', 10), ('Anagnostopoulos', 10), ('Andreou', 10), ('Angelopoulos', 10), ('Antoniou', 10), ('Apostolou', 10), ('Athanasiou', 10), ('Christodoulou', 10), ('Christou', 10), ('Dimitriou', 10), ('Dimopoulos', 10), ('Economou', 10), ('Fotiou', 10), ('Georgiou', 10), ('Giannopoulos', 10), ('Hatzis', 10), ('Ioannou', 10), ('Kalantzis', 10), ('Kapetanakis', 10), ('Karagiannis', 10), ('Katsaros', 9), ('Kokkinos', 9), ('Konstantinidis', 9), ('Kontos', 9), ('Kostopoulos', 9), ('Kyriakou', 9), ('Lambrou', 9), ('Makris', 9), ('Manolis', 9), ('Michalopoulos', 9), ('Nikolaidis', 9), ('Nikolaou', 9), ('Panagiotopoulos', 9), ('Papadakis', 9), ('Papadopoulos', 9), ('Papageorgiou', 9), ('Pappas', 9), ('Paraskevopoulos', 9), ('Petrou', 9), ('Politis', 9), ('Raptis', 8), ('Sarantos', 8), ('Sideris', 8), ('Spanos', 8), ('Stamatis', 8), ('Stavrou', 8), ('Stefanidis', 8), ('Theodorou', 8), ('Triantafyllou', 8), ('Tsakalos', 8), ('Vasilakis', 8), ('Vlahos', 8), ('Xenos', 8), ('Zervas', 8), ('Zografos', 8), ('Andrianopoulos', 8), ('Kouris', 8), ('Manousakis', 8), ('Sotiriou', 8), ('Vergos', 8)],
    "ITALIAN": [('Amato', 10), ('Barbaro', 10), ('Bartolo', 10), ('Bellini', 10), ('Benedetto', 10), ('Bianchi', 10), ('Bonanno', 10), ('Brunetti', 10), ('Caruso', 10), ('Casella', 10), ('Catalano', 10), ('Cavallaro', 10), ('Colombo', 10), ('Conti', 10), ('Costa', 10), ("D'Agostino", 10), ("D'Amico", 10), ('De Angelis', 10), ('De Luca', 10), ('Del Vecchio', 10), ('Di Marco', 10), ('Esposito', 10), ('Fabbri', 10), ('Ferraro', 10), ('Ferro', 10), ('Fiore', 10), ('Fontana', 10), ('Gallo', 9), ('Gatto', 9), ('Gentile', 9), ('Giordano', 9), ('Grasso', 9), ('Greco', 9), ('Guerra', 9), ('Lombardi', 9), ('Longo', 9), ('Mancini', 9), ('Marchetti', 9), ('Mariani', 9), ('Marino', 9), ('Martini', 9), ('Mazza', 9), ('Messina', 9), ('Milani', 9), ('Monaco', 9), ('Montagna', 9), ('Morelli', 9), ('Moretti', 9), ('Napolitano', 9), ('Orlando', 9), ('Palumbo', 9), ('Parisi', 9), ('Pellegrino', 9), ('Perri', 9), ('Pisano', 8), ('Rinaldi', 8), ('Riva', 8), ('Rizzo', 8), ('Romano', 8), ('Rossi', 8), ('Ruggiero', 8), ('Russo', 8), ('Sala', 8), ('Salerno', 8), ('Sanna', 8), ('Santoro', 8), ('Sartori', 8), ('Serra', 8), ('Silvestri', 8), ('Sorrentino', 8), ('Testa', 8), ('Valentino', 8), ('Vitale', 8), ('Zanetti', 8), ('Battaglia', 8), ('Calabrese', 8), ('Farina', 8), ('Lo Bianco', 8), ('Marchese', 8), ('Trimboli', 8)],
    "KOREAN": [('Kim', 10), ('Lee', 10), ('Park', 10), ('Choi', 10), ('Jung', 10), ('Kang', 10), ('Cho', 10), ('Yoon', 10), ('Jang', 10), ('Lim', 10), ('Han', 10), ('Shin', 10), ('Oh', 10), ('Seo', 10), ('Kwon', 10), ('Hwang', 10), ('Ahn', 10), ('Song', 10), ('Ryu', 10), ('Hong', 10), ('Go', 10), ('Mun', 10), ('Yang', 10), ('Son', 10), ('Bae', 10), ('Baek', 10), ('Jo', 10), ('Yoo', 10), ('Heo', 9), ('Nam', 9), ('Im', 9)],
    "SE_ASIAN": [('Boonmee', 10), ('Chaiyasit', 10), ('Intharat', 10), ('Kaewsai', 10), ('Phromma', 10), ('Rattanasuk', 10), ('Sae-Lim', 10), ('Sae-Tang', 10), ('Srisai', 10), ('Suwannarat', 10), ('Thongdee', 10), ('Wongsawat', 10), ('Jaidee', 10), ('Kongsri', 10), ('Saetang', 10), ('Siriwan', 10), ('Somboon', 10), ('Wattana', 10), ('Chea', 9), ('Heng', 9), ('Keo', 9), ('Khim', 9), ('Meas', 9), ('Pich', 9), ('Prak', 9), ('Sok', 9), ('Sorn', 9), ('Suon', 9), ('Tep', 9), ('Thach', 9), ('Ung', 9), ('Vong', 9), ('Yos', 9), ('Abdullah', 9), ('Hakim', 9), ('Hamzah', 9), ('Ibrahim', 8), ('Ismail', 8), ('Mahmud', 8), ('Osman', 8), ('Rahman', 8), ('Salleh', 8), ('Sulaiman', 8), ('Wijaya', 8), ('Santoso', 8), ('Setiawan', 8), ('Kusuma', 8), ('Hartono', 8), ('Pranoto', 8), ('Chanthavong', 8), ('Phanthavong', 8), ('Sisouk', 8), ('Vongsa', 8), ('Xaysana', 8)],
}

DIMINUTIVES: dict[str, list[str]] = {
    "William": ["Bill", "Will", "Billy", "Willie"],
    "Margaret": ["Maggie", "Peg", "Marg", "Marge"],
    "David": ["Dave", "Davey"],
    "Matthew": ["Matt", "Matty"],
    "Rebecca": ["Bec", "Becks", "Becky"],
    "Samantha": ["Sam", "Sammy"],
    "Jonathan": ["Jono", "Jon"],
    "James": ["Jim", "Jimmy", "Jamie"],
    "Robert": ["Rob", "Bob", "Bobby", "Robbie"],
    "John": ["Johnny", "Jack"],
    "Michael": ["Mike", "Mick", "Mikey"],
    "Richard": ["Rich", "Rick", "Dick", "Ricky"],
    "Charles": ["Charlie", "Chuck"],
    "Joseph": ["Joe", "Joey"],
    "Thomas": ["Tom", "Tommy", "Tommo"],
    "Christopher": ["Chris"],
    "Daniel": ["Dan", "Danny"],
    "Paul": ["Pauly"],
    "Mark": ["Marko"],
    "Donald": ["Don", "Donny"],
    "George": ["Georgie"],
    "Kenneth": ["Ken", "Kenny"],
    "Steven": ["Steve", "Stevie"],
    "Edward": ["Ed", "Eddie", "Ted", "Teddy"],
    "Brian": ["Bri"],
    "Ronald": ["Ron", "Ronnie"],
    "Anthony": ["Tony", "Ant"],
    "Kevin": ["Kev", "Kevvy"],
    "Jason": ["Jase"],
    "Gary": ["Gaz", "Gazza"],
    "Timothy": ["Tim", "Timmy"],
    "Larry": ["Lazza"],
    "Jeffrey": ["Jeff", "Jeffy"],
    "Frank": ["Frankie"],
    "Scott": ["Scotty"],
    "Eric": ["Rick"],
    "Stephen": ["Steve", "Stevie"],
    "Andrew": ["Andy"],
    "Raymond": ["Ray"],
    "Gregory": ["Greg"],
    "Joshua": ["Josh"],
    "Dennis": ["Den", "Denny"],
    "Walter": ["Walt", "Wally"],
    "Patrick": ["Pat", "Paddy"],
    "Peter": ["Pete"],
    "Harold": ["Harry", "Hal"],
    "Douglas": ["Doug", "Dougie"],
    "Henry": ["Harry"],
    "Carl": ["Carly"],
    "Arthur": ["Art", "Artie"],
    "Ryan": ["Ry"],
    "Roger": ["Roge"],
    "Joe": ["Joey"],
    "Juan": ["Johnny"],
    "Jack": ["Jacko"],
    "Albert": ["Al", "Bert", "Albie"],
    "Justin": ["Juzza"],
    "Terry": ["Tel"],
    "Gerald": ["Gerry"],
    "Keith": ["Keithy"],
    "Samuel": ["Sam", "Sammy"],
    "Ralph": ["Ralphie"],
    "Lawrence": ["Larry", "Loz"],
    "Nicholas": ["Nick", "Nicky"],
    "Roy": ["Royboy"],
    "Benjamin": ["Ben", "Benjy", "Benny"],
    "Bruce": ["Brucey"],
    "Brandon": ["Bran"],
    "Adam": ["Adsy", "Ads"],
    "Harry": ["Hazza"],
    "Fred": ["Freddy"],
    "Wayne": ["Wayno"],
    "Billy": ["Bill"],
    "Steve": ["Stevo"],
    "Louis": ["Lou", "Louie"],
    "Jeremy": ["Jez", "Jezza"],
    "Aaron": ["Azza"],
    "Howard": ["Howie"],
    "Eugene": ["Gene"],
    "Carlos": ["Carl"],
    "Russell": ["Russ", "Rusty"],
    "Bobby": ["Bob"],
    "Victor": ["Vic"],
    "Martin": ["Marty"],
    "Ernest": ["Ernie"],
    "Phillip": ["Phil", "Philly"],
    "Craig": ["Craigy"],
    "Alan": ["Al"],
    "Shawn": ["Shawny"],
    "Clarence": ["Clarrie"],
    "Sean": ["Seany"],
    "Jean": ["Jeanie"],
    "Christian": ["Chris"],
    "Johnson": ["Johno"],
    "Sharon": ["Shaz", "Shazza"],
    "Barry": ["Bazza"],
    "Warren": ["Waz", "Wazza"],
    "Darren": ["Daz", "Dazza"],
    "Gareth": ["Gaz", "Gazza"],
    "Cheryl": ["Chez", "Chezza"],
    "Corinne": ["Coz", "Cozza"],
    "Mary": ["Mare"],
    "Patricia": ["Pat", "Patsy", "Trish"],
    "Linda": ["Lin"],
    "Barbara": ["Barb", "Babs"],
    "Elizabeth": ["Liz", "Lizzy", "Beth", "Bess", "Bessie"],
    "Jennifer": ["Jen", "Jenny"],
    "Susan": ["Sue", "Susie"],
    "Dorothy": ["Dot", "Dottie"],
    "Lisa": ["Lis"],
    "Nancy": ["Nan"],
    "Karen": ["Kaz", "Kazza"],
    "Betty": ["Bet"],
    "Helen": ["Hels"],
    "Sandra": ["Sandy", "San"],
    "Donna": ["Don"],
    "Carol": ["Caz"],
    "Ruth": ["Ruthie"],
    "Michelle": ["Mich", "Shelley"],
    "Laura": ["Loz", "Lozza"],
    "Sarah": ["Sas", "Sasha", "Sally"],
    "Kimberly": ["Kim", "Kimmy"],
    "Deborah": ["Deb", "Debbie"],
    "Jessica": ["Jess", "Jessie"],
    "Shirley": ["Shirl"],
    "Cynthia": ["Cindy"],
    "Angela": ["Ange"],
    "Melissa": ["Mel"],
    "Brenda": ["Bren"],
    "Amy": ["Ames"],
    "Anna": ["Annie"],
    "Virginia": ["Ginny"],
    "Kathleen": ["Kathy", "Kath"],
    "Pamela": ["Pam", "Pammy"],
    "Martha": ["Marty"],
    "Debra": ["Deb", "Debbie"],
    "Amanda": ["Mandy"],
    "Stephanie": ["Steph"],
    "Carolyn": ["Caz"],
    "Christine": ["Chris", "Chrissy"],
    "Marie": ["Ree"],
    "Janet": ["Jan"],
    "Catherine": ["Cath", "Cathy", "Cate"],
    "Frances": ["Fran", "Franny"],
    "Ann": ["Annie"],
    "Joyce": ["Joy"],
    "Diane": ["Di"],
    "Alice": ["Ally"],
    "Julie": ["Jules"],
    "Heather": ["Heath"],
    "Teresa": ["Teri"],
    "Doris": ["Dor"],
    "Gloria": ["Glor"],
    "Evelyn": ["Evie"],
    "Mildred": ["Millie"],
    "Katherine": ["Kath", "Kathy", "Kat", "Kate", "Katie"],
    "Joan": ["Joanie"],
    "Ashley": ["Ash"],
    "Judith": ["Judy", "Jude"],
    "Rose": ["Rosie"],
    "Janice": ["Jan"],
    "Kelly": ["Kel"],
    "Nicole": ["Nic", "Nikki"],
    "Judy": ["Jude"],
    "Christina": ["Chris", "Chrissy", "Tina"],
    "Kathy": ["Kath"],
    "Theresa": ["Terry"],
    "Beverly": ["Bev"],
    "Tammy": ["Tam"],
    "Irene": ["Rene"],
    "Jane": ["Janey"],
    "Lori": ["Loz"],
    "Rachel": ["Rach"],
    "Marilyn": ["Mal", "Maz"],
    "Andrea": ["Ange", "Andi"],
    "Kathryn": ["Kath", "Kathy"],
    "Louise": ["Lou"],
    "Sara": ["Sas"],
    "Anne": ["Annie"],
    "Jacqueline": ["Jackie"],
    "Wanda": ["Wan"],
    "Bonnie": ["Bon"],
    "Frederick": ["Fred", "Freddie", "Fritz"],
    "Theodore": ["Ted", "Theo"],
    "Victoria": ["Vicky", "Vick", "Tori"],
    "Vincent": ["Vince", "Vinnie"],
    "Bernard": ["Bernie", "Barney"],
    "Leonard": ["Len", "Lenny", "Leo"],
    "Stanley": ["Stan"],
    "Eleanor": ["Ellie", "Nell", "Nora"],
    "Josephine": ["Jo", "Josie"],
    "Rosemary": ["Rose", "Rosie", "Rosy"],
    "Veronica": ["Ronnie", "Vera"],
    "Clifford": ["Cliff"],
    "Desmond": ["Des", "Dessie"],
    "Malcolm": ["Mal"],
    "Rajesh": ["Raj"],
    "Harpreet": ["Harry"],
    "Gurpreet": ["Gurp"],
    "Amit": ["Ami"],
    "Xiaoming": ["Xiao", "Ming"],
    "Junjie": ["Jun", "Jay"],
}

SURNAME_VARIANTS: dict[str, list[str]] = {
    "Smith": ["Smyth", "Smythe"],
    "Thompson": ["Thomson"],
    "Clark": ["Clarke"],
    "Wilson": ["Willson"],
    "Taylor": ["Tailor"],
    "Robertson": ["Robinson", "Roberson"],
    "Reid": ["Reed", "Read"],
    "Stewart": ["Stuart"],
    "Nguyen": ["Ngyuen", "Nguyan"],
    "Singh": ["Sing"],
    "Patel": ["Patell", "Pattel"],
    "Chen": ["Chan", "Chin"],
    "Ng": ["Ngu", "Eng"],
    "Wang": ["Wong", "Whang"],
    "Kim": ["Kimm"],
    "Papadopoulos": ["Papadopolous", "Papadopulos"],
    "Haddad": ["Hadad", "Haddaad"],
    "Anderson": ["Andersen"],
    "White": ["Whyte"],
    "Jackson": ["Jaxon"],
    "Harris": ["Harriss", "Haris"],
    "Martin": ["Marten", "Martyn"],
    "Robinson": ["Robison"],
    "Lewis": ["Louis"],
    "Lee": ["Lea", "Leigh"],
    "Walker": ["Wallker"],
    "Allen": ["Allan", "Alen"],
    "Young": ["Yong"],
    "King": ["Kinge"],
    "Wright": ["Right", "Write"],
    "Hill": ["Hil"],
    "Scott": ["Scot"],
    "Green": ["Greene"],
    "Adams": ["Addams"],
    "Baker": ["Barker", "Bacar"],
    "Nelson": ["Neilson"],
    "Carter": ["Karter"],
    "Mitchell": ["Michell", "Mitchel"],
    "Roberts": ["Robarts"],
    "Turner": ["Turnor"],
    "Phillips": ["Philips"],
    "Campbell": ["Campbel"],
    "Parker": ["Parka"],
    "Evans": ["Evens"],
    "Edwards": ["Edwardes"],
    "Collins": ["Colins"],
    "Stewart": ["Stuart"],
    "Morris": ["Morrice", "Moris"],
    "Rogers": ["Rodgers"],
    "Reed": ["Read", "Reid"],
    "Cook": ["Cooke"],
    "Morgan": ["Morgen"],
    "Bell": ["Bel"],
    "Murphy": ["Murphey"],
    "Bailey": ["Bailee", "Baily"],
    "Cooper": ["Couper"],
    "Richardson": ["Richardsen"],
    "Cox": ["Cocks"],
    "Howard": ["Howell", "Howarth"],
    "Ward": ["Word"],
    "Peterson": ["Petersen", "Pietersen"],
    "Gray": ["Grey"],
    "James": ["Jame"],
    "Watson": ["Whatson"],
    "Brooks": ["Brookes"],
    "Kelly": ["Kelley"],
    "Sanders": ["Saunders"],
    "Price": ["Pryce"],
    "Bennett": ["Bennet"],
    "Wood": ["Woods"],
    "Barnes": ["Barns"],
    "Ross": ["Rosse"],
    "Henderson": ["Hendersen"],
    "Coleman": ["Colman"],
    "Jenkins": ["Jenkyn", "Jenkyns"],
    "Perry": ["Parry"],
    "Powell": ["Powel"],
    "Long": ["Longe"],
    "Patterson": ["Paterson"],
    "Hughes": ["Hews", "Hughs"],
    "Washington": ["Washinton"],
}

TRANSLITERATION_FORENAMES: list[list[str]] = [
    ["Xiaoming", "Xiao Ming", "Hsiao-Ming", "Siu Ming"],
    ["Junjie", "Jun Jie", "Jun-jie", "Chun-chieh"],
    ["Xiaoli", "Xiao Li", "Hsiao-Li", "Siu Li"],
    ["Zhiqiang", "Zhi Qiang", "Chih-chiang", "Chi Keung"],
    ["Jian", "Chien", "Kin"],
    ["Min-jun", "Minjun", "Min Jun", "Minjoon"],
    ["Ji-woo", "Jiwoo", "Ji Woo", "Jeewoo"],
    ["Seo-yeon", "Seoyeon", "Seo Yeon", "Suhyeon"],
    ["Ha-joon", "Hajoon", "Ha Joon"],
    ["Do-yoon", "Doyoon", "Do Yoon"],
    ["Rajesh", "Rajes", "Raj"],
    ["Harpreet", "Harprit"],
    ["Gurpreet", "Gurprit"],
    # Arabic and Greek romanise inconsistently across sources, which is
    # exactly the drift this case is about. All-male on purpose: the case
    # runner in generate.py infers gender from the FIRST spelling against a
    # literal set, so a female family whose lead spelling is not in that set
    # would silently be emitted as male.
    ["Mohamad", "Mohammed", "Muhammad", "Mohammad", "Mohamed"],
    ["Youssef", "Yousef", "Yusuf", "Yousuf"],
    ["Hussein", "Husayn", "Hussain", "Husein"],
    ["Khaled", "Khalid", "Khaleed"],
    ["Ioannis", "Yiannis", "Yannis", "Giannis"],
    ["Georgios", "Yeorgios", "Giorgos", "Yorgos"],
    ["Krishnan", "Krishna", "Krishnen"]
]

TRANSLITERATION_SURNAMES: list[list[str]] = [
    ["Chowdhury", "Choudhury", "Choudhari", "Chaudhary", "Chaudhari"],
    ["Nguyen", "Ngyen", "Nguyan"],
    ["Krishnan", "Krishna"],
    ["Patel", "Patell"],
    ["Wong", "Wang", "Whang", "Huang", "Hwang"],
    ["Chen", "Chan", "Chin", "Tan", "Tang"],
    ["Lee", "Li", "Rhee", "Yi"],
    ["Zhang", "Cheung", "Chang"],
    ["Liu", "Lau"],
    ["Yang", "Yeung", "Young"],
    ["Wu", "Ng"],
    ["Zhao", "Chiu", "Cho"],
    ["Zhou", "Chau", "Chou"],
    # Arabic and Greek surname families, so the forename and surname strides
    # can land a coherent pair rather than always crossing populations.
    ["Khoury", "Khouri", "Khuri", "El-Khoury"],
    ["Haddad", "Hadad", "Al-Haddad"],
    ["El-Masri", "Elmasri", "Al-Masri", "El Masri"],
    ["Georgiou", "Yeorgiou", "Giorgiou"],
    ["Papadopoulos", "Papadopulos", "Papadopoylos"]
]

# DIACRITIC_FORENAMES / DIACRITIC_SURNAMES
#
# These pools feed the DIACRITIC_VARIANT case, so every entry MUST carry a
# diacritic -- that is the whole point of the case. On the
# "normalisation only" half the accent is the ONLY difference between two
# records, so an unaccented entry silently turns that instance into two
# identical records and the case stops proving anything.
#
# "Carries a diacritic" means the §5.3 definition, not just "has a combining
# mark": NFKD decomposes most of these, but a handful are single code points
# with NO canonical decomposition and NFKD leaves them completely untouched.
# The pools deliberately exercise all of them:
#
#   Ł  Łukasz, Łucja, Małgorzata, Kozłowski, Pawłowski, Jabłoński,
#      Kołodziej, Głowacki
#   ø  Søren, Sørensen, Østergaard
#   Đ  Đức, Đặng, Đỗ
#   ß  Weiß
#
# Łukasz is the worked example on the slide: without the special-case fold
# table it folds to "Łukasz", the "you fix this with NFKD, not with a
# language model" line stops being true, and the slide becomes a lie. If
# someone removes it, the regression it was there to catch goes unnoticed.
#
# They are drawn deliberately from safe categories:
#
#   1. Ordinary given names in the accented orthography their speakers
#      actually use (José, Renée, Zoë, Chloé, Björn, Hương, Đức).
#   2. High-frequency surnames from the same communities (García,
#      Fernández, Müller, Nguyễn, Trần, Wójcik, Kamiński, Horváth).
#
# Both are routine reference data -- the content of a census name-frequency
# table -- and both are common enough that no single real person is called
# to mind by either half on its own.
#
# DELIBERATELY EXCLUDED, and the reasoning is general rather than tied to
# any one language:
#   · Dictionary words that are not names. An accented word is not thereby
#     a name, and putting one on a customer's screen as a customer name is
#     the single most damaging error this dataset could make.
#   · Names of religious figures, deities and heads of state.
#   · Names of peoples, places and institutions. A demonym is not a person.
#   · Brand names, which are disproportionately accented (§9).
#
# A name being innocuous in isolation is NOT sufficient. Two safe halves can
# still compose a real public figure, and the fix for that is the
# forbidden-COMBINATION check in generate.py, not a pool change -- because
# neither half is wrong on its own. Do not try to solve it here.
#
# The forename and surname pools SHARE entries on purpose where the sharing
# is genuine: Hoàng and Vũ are both Vietnamese given names and Vietnamese
# surnames. That means the fixed stride can put the same word in both halves
# and emit "Hoàng Hoàng". Both halves are pinned before make_person sees
# them, so its guard cannot redraw; the deterministic surname-stepping loop
# in generate.py steps the surname on instead. Keep that loop.

DIACRITIC_FORENAMES: list[str] = [
    # Male
    "José", "Łukasz", "Michał", "Paweł", "Rafał", "Sławomir", "Björn",
    "Søren", "Jörg", "Jürgen", "Mikaël", "Sébastien", "Ramón", "Jesús",
    "Andrés", "Adrián", "Martín", "Óscar", "Rubén", "Joaquín", "Nicolás",
    "Iván", "Álvaro", "Tomáš", "Miloš", "Željko", "László", "Zoltán",
    "Márton", "Đức", "Dũng", "Hưng", "Tuấn", "Quốc", "Bảo", "Hải",
    "Gökhan", "Özgür",
    # Female
    "Renée", "Zoë", "Chloé", "Amélie", "Noémie", "Céline", "Hélène",
    "Désirée", "Åsa", "Beáta", "Terézia", "Mária", "Éva", "Ágnes",
    "Małgorzata", "Łucja", "Begoña", "Inés", "Belén", "Rocío", "Lucía",
    "Sofía", "María", "Hồng", "Hương", "Thủy", "Mỹ", "Hà", "Ngọc", "Thảo",
    "Trâm", "Quỳnh", "Snježana",
    # Genuine in either position -- see the note above on reduplication.
    "Hoàng", "Vũ",
]

DIACRITIC_SURNAMES: list[str] = [
    # Spanish / Portuguese
    "García", "Fernández", "Hernández", "Rodríguez", "Martínez", "González",
    "López", "Pérez", "Sánchez", "Ramírez", "Gómez", "Muñoz", "Ibáñez",
    "Gonçalves", "Simões", "Conceição",
    # German / Nordic
    "Müller", "Schröder", "Schäfer", "Weiß", "Sørensen", "Østergaard",
    "Lindström", "Åkesson",
    # Polish
    "Wójcik", "Kamiński", "Zieliński", "Szymański", "Woźniak", "Dąbrowski",
    "Kozłowski", "Pawłowski", "Jabłoński", "Stępień", "Górski", "Wróbel",
    "Kołodziej", "Brzeziński", "Głowacki", "Zając", "Król",
    # Czech / Slovak / Hungarian / South Slavic
    "Novák", "Horváth", "Tóth", "Szabó", "Kovács", "Németh", "Šimić",
    "Kovačić", "Jurić", "Perić", "Tomić", "Marić",
    # Vietnamese
    "Nguyễn", "Trần", "Phạm", "Đặng", "Võ", "Đỗ", "Lê",
    # French / Turkish
    # Turkish dotless ı (U+0131) is deliberately absent: NFKD does not fold
    # it and §5.3's special-case table does not cover it, so a name like
    # "Yılmaz" would fold to itself and the normalisation-only half would
    # emit two identical records instead of an accented/folded pair.
    "Lefèvre", "Gérard", "Chrétien", "Öztürk", "Şahin", "Özdemir", "Çelik",
    # Genuine in either position -- see the note above on reduplication.
    "Hoàng", "Vũ",
]

NAME_ORDER_FAMILIES: list[tuple[str, str, str]] = [
    ("Chen", "Wei", "Grace"),
    ("Kim", "Min-jun", ""),
    ("Wang", "Xiaoli", "Lily"),
    ("Park", "Ji-woo", "Jenny"),
    ("Nguyen", "Thi Mai", "Amy"),
    ("Li", "Hao", "Kevin"),
    ("Zhang", "Jie", ""),
    ("Liu", "Yi", "Alice"),
    ("Chen", "Ming", "Michael"),
    ("Yang", "Hui", ""),
    ("Huang", "Jian", "James"),
    ("Zhao", "Bo", "Brian"),
    ("Wu", "Lei", "Ray"),
    ("Zhou", "Xin", "Steve"),
    ("Xu", "Jun", ""),
    ("Sun", "Ping", "Penelope"),
    ("Ma", "Tao", "Tom"),
    ("Zhu", "Qiang", ""),
    ("Hu", "Cheng", "Charles"),
    ("Guo", "Bin", "Ben"),
    ("Lee", "Seo-jun", "Sam"),
    ("Choi", "Do-yoon", "Daniel"),
    ("Jung", "Ye-jun", ""),
    ("Kang", "Si-woo", "Sean"),
    ("Cho", "Ha-joon", ""),
    ("Yoon", "Joo-won", "Jason"),
    ("Jang", "Ji-ho", "Jeremy"),
    ("Tran", "Tuan", "Tony"),
    ("Le", "Minh", "Mike"),
    ("Pham", "Hung", "Harry"),
    ("Huynh", "Dung", ""),
    ("Hoang", "Mai", "Mary"),
    # --- Extended set -----------------------------------------------------
    # The pool must be at least as large as --case-instances, because
    # NAME_ORDER and NAME_ORDER_TRAP both index it and NAME_ORDER_TRAP
    # creates two people per instance. Reusing a family produces different
    # people carrying identical names, which makes the trap unanswerable
    # rather than difficult.
    ("Chen", "Yu", "Eugene"),
    ("Chen", "Lan", "Lana"),
    ("Wang", "Fang", "Fiona"),
    ("Wang", "Gang", ""),
    ("Wang", "Shu", "Susan"),
    ("Li", "Na", "Nina"),
    ("Li", "Qiang", ""),
    ("Li", "Xiaoming", "Simon"),
    ("Zhang", "Wei", "William"),
    ("Zhang", "Yan", "Yvonne"),
    ("Zhang", "Peng", "Paul"),
    ("Liu", "Fen", "Fay"),
    ("Liu", "Kai", "Kyle"),
    ("Liu", "Xue", "Snow"),
    ("Yang", "Chao", ""),
    ("Yang", "Ling", "Linda"),
    ("Huang", "Mei", "May"),
    ("Huang", "Zhen", ""),
    ("Zhao", "Juan", "Joan"),
    ("Zhao", "Lin", "Lynn"),
    ("Wu", "Hua", "Howard"),
    ("Wu", "Yun", "Yolanda"),
    ("Zhou", "Dan", "Danny"),
    ("Zhou", "Qing", ""),
    ("Xu", "Hong", "Holly"),
    ("Xu", "Long", "Leo"),
    ("Sun", "Yi", "Ivy"),
    ("Sun", "Xiaoyun", "Sharon"),
    ("Ma", "Jing", "Jean"),
    ("Ma", "Rui", "Ray"),
    ("Zhu", "Li", "Lisa"),
    ("Zhu", "Feng", ""),
    ("Hu", "Xia", "Summer"),
    ("Hu", "Yong", "Young"),
    ("Guo", "Mei", "Maggie"),
    ("Guo", "Tian", "Tina"),
    ("Lin", "Jia", "Jessie"),
    ("Lin", "Zhi", ""),
    ("He", "Ying", "Emily"),
    ("He", "Kun", ""),
    ("Gao", "Yuan", "Yvette"),
    ("Gao", "Bing", "Bill"),
    ("Liang", "Shan", "Shannon"),
    ("Liang", "Hui", "Hugh"),
    ("Zheng", "Xiaohua", "Sophie"),
    ("Zheng", "Wen", "Wendy"),
    ("Luo", "Ting", "Tiffany"),
    ("Luo", "Hao", ""),
    ("Song", "Yue", "Yvonne"),
    ("Song", "Jian", "Jack"),
    ("Xie", "Ping", ""),
    ("Xie", "Lu", "Lucy"),
    ("Tang", "Min", "Mindy"),
    ("Tang", "Gang", "Gary"),
    ("Han", "Xiaoli", "Shirley"),
    ("Han", "Bo", "Bob"),
    ("Cao", "Yan", "Ann"),
    ("Cao", "Jun", "June"),
    ("Deng", "Hui", "Helen"),
    ("Deng", "Wei", ""),
    ("Feng", "Qi", "Chris"),
    ("Feng", "Xiu", "Sue"),
    ("Cai", "Ling", "Lena"),
    ("Cai", "Zhong", ""),
    ("Shen", "Yi", "Eva"),
    ("Shen", "Hai", "Harvey"),
    ("Kim", "Seo-yeon", "Sarah"),
    ("Kim", "Ji-hoon", "Jim"),
    ("Kim", "Ha-eun", "Hannah"),
    ("Lee", "Ji-woo", "Julie"),
    ("Lee", "Min-seo", ""),
    ("Lee", "Joon-ho", "John"),
    ("Park", "Seo-jun", "Peter"),
    ("Park", "Ha-yoon", "Hayley"),
    ("Park", "Dong-hyun", ""),
    ("Choi", "Ye-eun", "Emma"),
    ("Choi", "Jin-woo", "Jin"),
    ("Jung", "Soo-ah", "Sua"),
    ("Jung", "Tae-yang", "Tay"),
    ("Kang", "Na-eun", "Nancy"),
    ("Kang", "Hyun-woo", ""),
    ("Cho", "Yu-jin", "Eugenia"),
    ("Cho", "Min-ho", "Matthew"),
    ("Yoon", "Seo-ah", "Sera"),
    ("Yoon", "Dae-sung", ""),
    ("Jang", "Eun-ji", "Angie"),
    ("Lim", "Sung-min", "Simon"),
    ("Lim", "Hye-jin", "Helen"),
    ("Shin", "Ji-eun", "Jean"),
    ("Shin", "Woo-jin", ""),
    ("Oh", "Seung-hyun", "Sean"),
    ("Oh", "Mi-rae", "Mira"),
    ("Seo", "Jae-won", "Jay"),
    ("Kwon", "Bo-ram", "Bora"),
    ("Hwang", "Ji-min", "Jamie"),
    ("Ahn", "Hyo-jin", ""),
    ("Bae", "Su-bin", "Sabine"),
    ("Nguyen", "Van Hung", "Henry"),
    ("Nguyen", "Thi Lan", "Lana"),
    ("Nguyen", "Quoc Anh", ""),
    ("Tran", "Thi Hoa", "Flora"),
    ("Tran", "Van Nam", ""),
    ("Le", "Thi Thu", "Thu"),
    ("Le", "Hoang Nam", "Nathan"),
    ("Pham", "Thi Ngoc", "Pearl"),
    ("Pham", "Van Duc", ""),
    ("Vu", "Thi Huong", "Hannah"),
    ("Vu", "Minh Quan", "Quentin"),
    ("Vo", "Thanh Tung", "Tony"),
    ("Dang", "Thi Lien", "Lily"),
    ("Bui", "Van Long", "Lonny"),
    ("Do", "Thi Trang", "Tracy"),
    ("Ngo", "Quang Huy", "Hugh"),
    ("Duong", "Thi Yen", "Jenny"),
    ("Truong", "Minh Tuan", ""),
    ("Dinh", "Thi Nga", "Nadia"),
]
