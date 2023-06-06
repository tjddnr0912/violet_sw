// Quiz No.1
func average( _ arr : Double...) -> Double?
{
	if arr.count == 0
	{
		return nil
	}
	else {
		var sum = 0.0
		for e in arr
		{
			sum += e
		}
		return sum / Double(arr.count)
	}
}

//let input = readLine()?.components(separatedBy: " ").map {Double(String($0))!}

if let no1 = average(3.1, 7.7, 9.6, 8.9)
//if let no1 = average()
{
	print(no1)
}

// Quiz No.2
func add(_ a : Int, _ b: Int) -> Int {return a + b}
func sub(_ a : Int, _ b: Int) -> Int {return a - b} 
func mul(_ a : Int, _ b: Int) -> Int {return a * b}
func calculate(_ v1: Int, _ v2: Int, op : (Int, Int) -> Int = add) -> Int
{
	return op(v1, v2)
}

var ret1 = calculate(10, 20, op : add)
print(ret1)

var ret2 = calculate(10, 20, op : sub)
var ret3 = calculate(10, 20, op : mul)
print(ret2)
print(ret3)


// Quiz No.3
class People
{
	var name: String
	var age: Int
	var gender: Gender
	var isAdult: Bool
	{
		get { return age > 18 }
	}

	init(name:String, age:Int, gender:Gender)
	{
		self.name = name
		self.age = age
		self.gender = gender
	}

	enum Gender {
		case Male
		case Female
	}

}
class Student : People, Hashable
{
	var id = 0

	init(name:String, age:Int, gender:Gender, id:Int)
	{
		self.id = id
		super.init(name:name, age:age, gender:gender)
	}

	convenience init(name:String, gender:Gender, id:Int)
	{
		self.init(name:name, age: 0, gender:gender, id:id)
	}

	override var age : Int
	{
		didSet(value)
		{
			print("change age", value, "to", age)
		}
	}

	func hash(into hasher: inout Hasher)
	{
		hasher.combine(id)
	}

	static func == (lhs: Student, rhs: Student) -> Bool
	{
		return lhs.id == rhs.id
	}

}

var s1 = Student(name : "kim", age : 20, gender : .Female, id : 10)
var s2 = Student(name : "kim", gender : .Male, id : 10)

print(s1.isAdult)
print(s2.isAdult)

s1.age = 30

var st : Set<Student> = []